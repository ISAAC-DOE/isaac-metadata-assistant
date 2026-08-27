"""HTTP endpoints for the local UI prototype (all JSON, prefixed ``/api``).

Every verdict is produced by an ``isaac_records`` core function — this module only
routes, serializes (via ``serialize``), and enforces the synthetic-only governance
boundary. It adds no validation logic and never mutates the truth path.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Mapping, Sequence

import logging

from fastapi import APIRouter, Body, Depends, Header, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from isaac_records.audit import audit_records, render_audit
from isaac_records.complete import (
    apply_answers,
    apply_corrections,
    is_descriptor_shaped,
    is_qc_shaped,
    is_series_shaped,
    is_sha256_shaped,
)
from isaac_records.draft_validator import UPLOADED_BY_PATH, validate_draft
from isaac_records.export import export_draft
from isaac_records.extract.draft_builder import build_draft
from isaac_records.extract.structured import FIELD_MAP as EXTRACTOR_FIELD_MAP
from isaac_records.ids import is_record_id, new_record_id
from isaac_records.models import user_confirmation
from isaac_records.exactness import check_exactness, combined_summary
from isaac_records.official import EXPECTED_VERSION, schema_path, validate_official
from isaac_records.portal_warnings import portal_warnings

from . import __version__
from . import assets
from . import assistant_query
from . import csv_ingest
from . import db_provider
from . import db_recon
from . import db_write
from . import dependencies
from . import conflict_resolution as cr
from . import evidence_classify
from . import experiment_repository
from . import identity as identity_module
from . import memory
from . import memory_graph
from . import notes
from . import provenance
from . import revision_history
from . import runtime_mode
from . import runtime_records
from . import search
from . import serialize
from . import sources
from . import submission_store
from . import submissions
from . import transcript_capture as tc
from . import record_attribution
from .providers import assistant as providers_assistant
from .providers import config as provider_config
from .providers import refusal as providers_refusal
from .providers import transcription as providers_transcription
from . import verification
from . import version_contract as vc
from . import workspace as ws
from .identity import require_human_actor
from .workflow import derive_lifecycle, derive_workflow
from .workspace import REPO_ROOT, Experiment, ExportUnit, atomic_write_text

router = APIRouter(prefix="/api")

_log = logging.getLogger("isaac_api.csv_ingest")

SCHEMA_LABEL = f"ISAAC v{EXPECTED_VERSION}"

_UPLOAD_BLOCKED = {
    "blocked": True,
    "reason": (
        # Slice 2A: was "…not enabled in this synthetic prototype." The refusal
        # itself is unchanged and still true; only the adjectival label moved,
        # because "this synthetic prototype" described the whole deployment
        # while the fact being stated is upload-scoped. Matches the frontend's
        # parallel fallback in `screens/LoadMaterials.tsx`.
        "Real or private data upload is approval-gated and not enabled in this "
        "workspace."
    ),
}


# --- OpenAPI documentation metadata (documentation-only) ----------------------
#
# Everything in this section is consumed by FastAPI only when it GENERATES the
# OpenAPI document. None of it is read at request time: it adds no handler,
# declares no new status code, and changes no parsing, validation, side effect, or
# response payload. Two rules keep the generated contract stable:
#
#   * ``422`` is declared here ONLY for an operation that has no path/query/body
#     parameter, i.e. one for which FastAPI generates no automatic validation-error
#     response. Declaring 422 on an operation that already has one would make
#     FastAPI SKIP its own entry and so silently drop the ``HTTPValidationError``
#     content ref (fastapi.openapi.utils.get_openapi_path). Those operations
#     document their semantic 422 in prose instead.
#   * Response *descriptions* only — never a model, schema, or status code.
#
# Wording rule: a consumer-facing ``description`` states what the operation
# returns and requires. Internal reasoning stays in the docstrings/comments below,
# which no longer reach OpenAPI once ``description=`` is set explicitly.

TAG_META = "Health & Meta"
TAG_EXPERIMENTS = "Experiments"
TAG_DRAFTS = "Drafts & Answers"
TAG_VALIDATION = "Validation"
TAG_EVIDENCE = "Evidence"
TAG_EXPORT = "Export & Artifacts"
TAG_MEMORY = "Project Memory"
TAG_GRAPH = "Graph"
TAG_SEARCH = "Search"
TAG_ASSISTANT = "Assistant"
TAG_DEMO = "Example Workspace"
TAG_INGESTION = "Ingestion"
TAG_UPLOADS = "Uploads"
TAG_SCHEMA = "Schema & Vocabulary"
TAG_TUTORIAL = "Worked Example Sessions"

#: Tag definitions registered on the app (``isaac_api.app.create_app`` passes this
#: as ``openapi_tags``). Every tag any route below uses appears here exactly once,
#: in the order the documentation should list the groups.
OPENAPI_TAGS: list[dict] = [
    {
        "name": TAG_META,
        "description": (
            "Liveness, deployment identity, and this API's own machine-readable "
            "description. Read-only."
        ),
    },
    {
        "name": TAG_EXPERIMENTS,
        "description": (
            "Listing and reading the experiments held in the workspace, plus a "
            "cross-record triage projection. Read-only."
        ),
    },
    {
        "name": TAG_DRAFTS,
        "description": (
            "Reading a record's draft fields and its open blocking questions, and "
            "answering or correcting them. The two write operations require an "
            "explicit user confirmation and the record's current revision."
        ),
    },
    {
        "name": TAG_VALIDATION,
        "description": (
            "Checking a record against the vendored official ISAAC schema, "
            "auditing exported artifacts, and the advisory non-gating warning "
            "channel. Every verdict comes from the deterministic core."
        ),
    },
    {
        "name": TAG_EVIDENCE,
        "description": (
            "The per-field evidence trail, its evidence-support classification, "
            "where each value came from and what establishes it, previews of the "
            "reference source files the evidence cites, and the conflicts a "
            "record's own evidence carries. Every operation here is read-only "
            "except the one that records a scientist's decision about a conflict, "
            "which stores that decision beside the evidence and changes no value."
        ),
    },
    {
        "name": TAG_EXPORT,
        "description": (
            "Producing an official ISAAC record plus its evidence sidecar, and "
            "reading the artifacts a completed export wrote."
        ),
    },
    {
        "name": TAG_MEMORY,
        "description": (
            "The Project Memory plane: indexed concepts and files. It returns "
            "leads to verify against the cited files, never a correctness ruling."
        ),
    },
    {
        "name": TAG_GRAPH,
        "description": (
            "Project Memory status and its deterministic reference-graph "
            "projection. Read-only, and never a correctness ruling."
        ),
    },
    {
        "name": TAG_SEARCH,
        "description": (
            "One grouped search envelope over the workspace (truth plane) and "
            "Project Memory (advisory leads), each group reported independently."
        ),
    },
    {
        "name": TAG_ASSISTANT,
        "description": (
            "Deterministic question answering over a fixed intent catalog. There "
            "is no language model: an unsupported question is refused rather than "
            "guessed, and nothing is ever mutated."
        ),
    },
    {
        "name": TAG_DEMO,
        "description": (
            "Running and resetting the committed built-in example records. Both "
            "operate only on the canonical example records and accept no "
            "caller-supplied ids or paths."
        ),
    },
    {
        "name": TAG_INGESTION,
        "description": (
            "Read-only preview of a campaign-sheet CSV reconciled against a "
            "record. Nothing is stored, indexed, or applied."
        ),
    },
    {
        "name": TAG_UPLOADS,
        "description": (
            "The governance seam for file upload. It always refuses; no file is "
            "read, parsed, or stored."
        ),
    },
    {
        "name": TAG_SCHEMA,
        "description": (
            "Read-only reference view of the vendored official ISAAC schema and "
            "the controlled vocabularies. No editing affordance exists."
        ),
    },
    {
        "name": TAG_TUTORIAL,
        "description": (
            # "the ordinary workspace holds no example records at all" was a claim
            # about the CONTENTS of a directory this API never inspects to say it.
            # ``list_experiments(None)`` enumerates whatever is on disk under the
            # workspace root and there is no startup migration, so a deployment whose
            # workspace survives an upgrade still holding the previously-seeded five
            # would serve them from the ordinary scope while this sentence denied
            # they were there. What is genuinely enforced is a REFUSAL, not merely a
            # required parameter: ``_materialise_seed``, ``reset_to_canonical_seed`` and
            # ``ensure_tutorial_seeded`` each raise ``InvalidTutorialSession`` on a
            # ``None`` session id, so no SEEDING path can create an example record
            # outside a session. That is what is stated.
            #
            # "NO CODE PATH IN THIS BUILD CAN" is what this comment used to claim, and it
            # was too strong: ``create_experiment(title, source, draft, id=SEED_READY_ID,
            # session_id=None)`` is exactly such a path — ``rid = id or new_record_id()``
            # (``workspace.py``), then ``exp.save()`` into ``scope_root(None)``. ("Requires
            # a session_id" was an even earlier justification and was weaker still:
            # ``scope_root(None)`` returns ``workspace_root()`` silently, and an explicit
            # ``session_id=None`` was measured writing a canonical record into the
            # ordinary root before the refusals were added.)
            #
            # THE JUSTIFICATION HAS NOW MOVED A SECOND TIME, AND THIS IS THE MOVE TO
            # READ CAREFULLY. It used to be "this build exposes no record-creation
            # surface at all — there is no ``POST /api/experiments``". **There is one
            # now.** That sentence is retired; the claim above is not, because the claim
            # is about BUILT-IN EXAMPLE records and the new route cannot make one.
            #
            # What carries it, in the order a reader should check it:
            #
            #  1. THE SEEDING REFUSALS. ``_materialise_seed``,
            #     ``reset_to_canonical_seed`` and ``ensure_tutorial_seeded`` each RAISE
            #     ``InvalidTutorialSession`` on a ``None`` session id. These are the only
            #     functions that know what an example record CONTAINS, and none of them
            #     can be aimed at the ordinary workspace.
            #  2. THE ID CANNOT BE CHOSEN. ``POST /api/experiments`` never passes ``id=``,
            #     so ``create_experiment`` mints a fresh ULID; and
            #     ``CreateExperimentRequest`` sets ``extra="forbid"``, so a client that
            #     sends one gets a 422 rather than having it ignored. The five canonical
            #     ids are fixed constants and are therefore unreachable from the route.
            #  3. THE DURABLE STORE REFUSES ONE ANYWAY.
            #     ``PostgresOrdinaryStore.refuse_if_not_persistable`` raises on any
            #     canonical id, in any scope, so an example cannot be made durable even
            #     if one were somehow materialised.
            #
            # ``test_tutorial_scope.py::test_create_experiment_has_no_caller_in_the_api_package``
            # still guards this — it now pins that there is exactly ONE caller, that the
            # caller passes neither ``id=`` nor ``session_id=``, and that no path can
            # materialise a canonical record into the ordinary scope. Adding a second
            # caller, or an ``id`` argument to this one, still fails.
            "Creating and discarding an isolated worked-example workspace. The "
            "built-in example records are created only inside one of these — no "
            "operation in this API materialises one into the ordinary workspace."
        ),
    },
]


_R_UNAUTHORIZED: dict = {
    401: {
        "description": (
            "The deployment requires an API key and the request did not present a "
            "valid one. Never returned when the deployment leaves this "
            "authentication disabled, which is the default for local runs."
        )
    },
}

_R_EXPERIMENT_NOT_FOUND: dict = {
    404: {
        "description": (
            "No experiment in the selected workspace has that id — or the "
            "`X-Isaac-Tutorial-Session` header named a worked-example session that "
            "does not exist. The request is never silently answered from the "
            "ordinary workspace instead."
        )
    },
}

_R_RUN_NOT_FOUND: dict = {
    404: {
        "description": (
            "No experiment in the selected workspace has that id, that experiment "
            "has no run with that id, or the `X-Isaac-Tutorial-Session` header "
            "named a worked-example session that does not exist. The request is "
            "never silently answered from the ordinary workspace instead."
        )
    },
}

#: THE DURABLE-STORAGE OUTAGE, DECLARED WHEREVER IT CAN HAPPEN.
#:
#: It was declared on ONE operation — ``POST /api/experiments``, and only for its
#: write — while ``workspace.load_experiment`` can raise it on every read that
#: resolves a record by id, and ``Experiment.save`` on every write. The contract
#: therefore said ``200, 304, 401, 404, 422`` for ``GET /api/experiments/{id}``
#: and the deployment answered ``503``: a client written against the document had
#: no reason to expect the one status that means "retry" rather than "your record
#: is gone", which is the same class of defect as the ``404`` that provoked all of
#: this — a true state the contract does not admit exists.
#:
#: THE SET IT IS APPLIED TO IS DERIVED, NOT CHOSEN: every operation whose handler
#: reaches ``ws.load_experiment`` or a write-through save. Two operations that
#: touch records are deliberately NOT in it. ``POST /api/demo/run`` refuses
#: ``scope is None`` before it loads anything, so its ``load_experiment`` always
#: carries a session id, and a session-scope read never consults the database.
#: ``POST /api/demo/reset`` addresses a session for the same reason. The
#: LIST-shaped reads (``GET /api/experiments``, ``GET /api/search``,
#: ``GET /api/runtime/records``) are not in it either, and that is the whole
#: design: they degrade rather than fail.
_R_STORAGE_UNAVAILABLE: dict = {
    503: {
        "description": (
            "This deployment stores experiments in its own database, and this "
            "server could not find out whether that database is holding this "
            "record — either it did not answer, or it answered and the server "
            "could not finish restoring its own working copies. Nothing was "
            "changed. The record may well exist; this response says the server "
            "could not find out, which is why it is not a `404`. **Whether a "
            "retry helps depends on which of the two happened, and the body says "
            "which**: a database that did not answer is usually temporary, since "
            "the next request opens a fresh connection, while a restore that "
            "could not finish generally needs a server-side fix. The body names "
            "no host, path or credential."
        )
    },
}

#: The optimistic-concurrency preconditions every write operation shares.
_R_PRECONDITION: dict = {
    400: {
        "description": (
            "The `If-Match` header was supplied but is not one or more strong "
            "quoted validators."
        )
    },
    412: {
        "description": (
            "`If-Match` did not match the record's current revision, so another "
            "writer changed it first and nothing was written. The response echoes "
            "the current `ETag` so a client can refresh in one further request."
        )
    },
    428: {
        "description": (
            "`If-Match` was omitted. Every write requires the header, so a write "
            "that never read the record is refused by default.\n\n"
            "ONE EXCEPTION, AND IT IS AN EXCEPTION TO THE STRONGEST FORM OF THAT "
            "SENTENCE. `If-Match: *` is accepted, and it means what RFC 9110 says "
            "it means — *if the resource exists* — so it does NOT compare "
            "revisions. A caller sending it can overwrite a record, or a run, that "
            "it has never read, and the write succeeds. That is deliberate and "
            "tested; it is stated here because this description previously read "
            "\"a blind overwrite is not possible\", which `*` makes false. If you "
            "want the concurrency guarantee, send the validator a read returned, "
            "never `*`."
        )
    },
}

# --- scope resolution: normal workspace vs. an isolated worked-example session --
#
# ONE dependency, reused by every record operation and by both example-workspace
# operations, so a route added later cannot accidentally omit it and silently read
# the normal workspace while the caller believed it was inside a session.
#
# THE FAIL-CLOSED PROPERTY. A header that is present but names no existing session
# is a 404. It is NEVER treated as "no header", because falling back to the normal
# workspace would answer a request about one scope with the contents of another —
# the caller would be told a record does not exist when it does, or (worse, once
# normal scope can hold real records) shown records it never asked for. A malformed
# header is a 422: it does not name a session at all.

#: The request header carrying the worked-example session id.
TUTORIAL_SESSION_HEADER = "X-Isaac-Tutorial-Session"

_TUTORIAL_HEADER_DESCRIPTION = (
    "Optional. The id of a worked-example session, as returned by "
    "`POST /api/tutorial/sessions`. Omit it to operate on the ordinary workspace. "
    "A malformed id is rejected with `422`, and an id that names no existing "
    "session with `404` — it never falls back to the ordinary workspace."
)

#: The refusal for an answer that belongs to a Run, on the RECORD's answer/edit
#: operations. Declared as its own constant because an undeclared status on a published
#: contract is a contract that is wrong: an independent review found all three routes
#: below emitting a live `409` that `EXPECTED_RESPONSE_CODES` did not list, so the guard
#: that exists to pin the contract was certifying one that omitted it.
_R_BELONGS_TO_A_RUN: dict = {
    409: {
        "description": (
            "This record has runs, and the answer names something a RUN owns — a "
            "spectrum, a QC verdict, a descriptor, or an asset hash. Answering it here "
            "would write a value no exported record reads, so nothing was written. The "
            "body names every run and the operation that can take the answer: "
            "`POST /api/experiments/{experiment_id}/runs/{run_id}/answers`.\n\n"
            "The absorption edge is NOT among them. It lives in the record's implicit "
            "derivations, which every run holding the record's values inherits, so "
            "answering it on the record does reach those runs. A run that has recorded "
            "any override does not receive it, and that is a limit of how derivations "
            "are inherited rather than something this refusal can fix."
        )
    },
}

#: The refusal for adding a Run to a record already exported under its own identity.
_R_ALREADY_EXPORTED_WITHOUT_RUNS: dict = {
    409: {
        "description": (
            "This record has already been exported under its own identity. Adding a run "
            "would move the exported identity onto the run and publish a second "
            "official record with the same science, and no operation withdraws the "
            "first, so nothing was written."
        )
    },
}

_R_TUTORIAL_SCOPE: dict = {
    404: {
        "description": (
            "Either no experiment in the selected workspace has that id, or the "
            "`X-Isaac-Tutorial-Session` header named a worked-example session that "
            "does not exist (it was discarded, or it expired). The request is never "
            "silently answered from the ordinary workspace instead."
        )
    },
}


class TutorialScopeError(Exception):
    """A scope-resolution refusal, carried out of a dependency as a typed response.

    A FastAPI dependency cannot return a response, only raise. This exception is
    translated by ``tutorial_scope_error_handler`` (registered by
    ``isaac_api.app.create_app``) into the same ``{"error": ...}`` body shape every
    other refusal in this module uses. The payload is path-free and never echoes
    the rejected id.
    """

    def __init__(self, status_code: int, payload: dict) -> None:
        super().__init__(payload.get("error", "tutorial_scope_error"))
        self.status_code = status_code
        self.payload = payload


async def tutorial_scope_error_handler(request, exc: TutorialScopeError) -> JSONResponse:
    """Render a :class:`TutorialScopeError` as its typed JSON body."""
    return JSONResponse(status_code=exc.status_code, content=exc.payload)


#: The typed body every durable-storage outage produces, whichever operation hit
#: it. One shape, one place, because the outage is a property of the deployment
#: rather than of the operation that happened to notice it.
STORAGE_UNAVAILABLE_ERROR = "experiment_storage_unavailable"


async def storage_unavailable_handler(request, exc) -> JSONResponse:
    """Render a durable-storage outage as a typed ``503``, never a bare 500.

    WHY 503 AND NOT 500. The request was well formed and the application is
    working; a dependency this deployment is configured to use did not answer.
    ``503`` says "try again", which is true — the write path opens a fresh
    connection every time and recovers by itself — where a 500 says "this is
    broken", which sends an operator looking in the wrong place.

    WHY NOT DEGRADE TO THE FILESYSTEM INSTEAD. Because the reader has been told,
    on the screen they created this from, that their work is stored durably. A
    quiet ephemeral write withdraws that promise without telling them and they
    find out at the next restart. Failing the write is the honest outcome, and
    ``GET /api/health`` stops claiming durability from the same moment.

    THE BODY NAMES NO HOST, PATH, USER OR DRIVER MESSAGE — the exception carries
    a fixed string for that reason (``experiment_repository.StorageUnavailable``).
    """
    return JSONResponse(
        status_code=503,
        content={
            "error": STORAGE_UNAVAILABLE_ERROR,
            "message": str(exc),
        },
    )


async def durable_write_conflict_handler(request, exc) -> JSONResponse:
    """The LAST RESORT for a refused durable write: still a 412, never a 500.

    The three mutation handlers render this themselves (``_save_versioned``),
    because only they hold the experiment and the client's ``If-Match`` and can
    therefore fill the whole body. This handler exists for the one call site that
    persists WITHOUT going through them — ``POST /api/experiments``, whose create
    reaches ``Experiment.save`` directly. Reaching it requires a ULID collision
    with a row carrying the same generation, which is not a case this application
    can produce; an unguarded call site for a new exception class is the defect,
    not the likelihood.

    SAME DISCRIMINATOR, SAME KEYS, HONEST NULLS. A client must not have to learn a
    second shape for one condition, so the body is ``_stale_write``'s key set
    exactly. ``expected_*`` are ``null`` because this path carries no client
    validator to echo — the honest answer, not a fabricated one — and the
    ``current_*`` pair is filled only from the winner's row when it can be read,
    never from the losing write.

    ``experiment_id`` COMES FROM THE EXCEPTION, NOT FROM THE ROW. It is known at
    every raise site, while the read-back can return nothing — and reading it out
    of ``stored_state`` alone emitted ``experiment_id: null`` in exactly the case
    a client most needs it named. ``_stale_write`` always carries a string; so
    does this.
    """
    state = exc.stored_state if isinstance(exc.stored_state, dict) else {}
    rev = state.get("rev")
    rev = rev if isinstance(rev, int) and not isinstance(rev, bool) else None
    generation = state.get("generation")
    version = f"{generation}.{rev}" if generation and rev is not None else None
    resp = JSONResponse(
        status_code=412,
        content={
            "error": "stale_write",
            "experiment_id": getattr(exc, "experiment_id", None) or state.get("id"),
            "expected_rev": None,
            "current_rev": rev,
            "expected_version": None,
            "current_version": version,
        },
    )
    if version is not None:
        resp.headers["ETag"] = f'"{version}"'
    return resp


def tutorial_scope(
    x_isaac_tutorial_session: Annotated[
        str | None,
        Header(alias=TUTORIAL_SESSION_HEADER, description=_TUTORIAL_HEADER_DESCRIPTION),
    ] = None,
) -> str | None:
    """Resolve the scope this request operates in.

    Returns ``None`` for the ordinary workspace, or the session id for a
    worked-example session. Raises :class:`TutorialScopeError` (422 malformed / 404
    unknown) rather than ever degrading to the ordinary workspace.
    """
    if x_isaac_tutorial_session is None:
        return None
    raw = x_isaac_tutorial_session.strip()
    if not ws.is_tutorial_session_id(raw):
        raise TutorialScopeError(
            422,
            {
                "error": "invalid_tutorial_session",
                "header": TUTORIAL_SESSION_HEADER,
                "message": (
                    "The worked-example session id is not of the expected form. "
                    "Create a session with POST /api/tutorial/sessions."
                ),
            },
        )
    if not ws.tutorial_session_exists(raw):
        raise TutorialScopeError(
            404,
            {
                "error": "tutorial_session_not_found",
                "header": TUTORIAL_SESSION_HEADER,
                "message": (
                    "That worked-example session does not exist — it was discarded "
                    "or it expired. Create a new one with "
                    "POST /api/tutorial/sessions. This request was not answered "
                    "from the ordinary workspace."
                ),
            },
        )
    return raw


#: The resolved scope, injected into every operation that reads or writes records.
TutorialScopeDep = Annotated[str | None, Depends(tutorial_scope)]


#: The path parameter naming an experiment. One description, used by every route
#: that takes it, so the wording cannot drift between operations.
ExperimentId = Annotated[
    str,
    Path(
        description=(
            "The id of an experiment in this workspace, as returned by "
            "`GET /api/experiments`."
        )
    ),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _not_found(experiment_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "experiment_not_found", "id": experiment_id},
    )


# --- If-Match precondition (P27.5-strict optimistic-concurrency contract) -----
#
# RFC 9110 strong comparison for unsafe methods: only strong quoted validators are
# accepted; weak (``W/"..."``) and malformed values are rejected 400. A mismatch is
# 412 stale_write (with the current ETag echoed so the client refreshes in one
# hop). A MISSING If-Match is now rejected 428 precondition_required — the
# one-release compatibility grace is retired (``vc.precondition_required()`` is
# True). No filesystem path, secret, or raw record content ever appears in a token
# or error body.

#: A strong ETag validator: a double-quoted opaque token, no ``W/`` prefix.
#:
#: ``\A``/``\Z`` NOT ``^``/``$``: Python's ``$`` also matches immediately before a
#: trailing newline, so ``^"..."$`` applied with ``.match()`` accepted ``'"abc"\n'``
#: as a well-formed strong validator. STATED HONESTLY, that was not reachable over
#: HTTP today — an ASGI server will not deliver a header value containing LF, and
#: both call sites below feed this ``part.strip()``, which removes a trailing newline
#: before the pattern ever sees it. The pattern is anchored anyway so the exactness
#: belongs to the constant rather than to two callers that happen to strip: a third
#: caller that reads a validator from anywhere but a header cannot reopen the hole.
_STRONG_TAG_RE = re.compile(r'\A"[^"\\]+"\Z')


def _expected_rev_from_token(token: str | None) -> int | None:
    """The integer after the LAST ``.`` of a client token, else ``None``."""
    if not token or "." not in token:
        return None
    try:
        return int(token.rsplit(".", 1)[-1])
    except (TypeError, ValueError):
        return None


def _precondition_identity(entity) -> dict:
    """The id keys a precondition body carries for whatever is being guarded.

    An :class:`Experiment` carries ``{"experiment_id": <its id>}`` — unchanged, and
    it is the ONLY shape any pre-existing caller produces, because ``Experiment``
    has no ``precondition_identity`` attribute and never gets one here.

    A RUN is guarded by the same three helpers below (its ``If-Match`` carries the
    RUN's validator, not its experiment's), and it needs two ids rather than one:
    filing a run id under the key ``experiment_id`` would be a false statement in
    the one body a client reads when a write is refused. So the guarded object may
    supply its own identity mapping and this is the single place that asks for it.
    Reusing the helpers rather than copying them is deliberate: a 428 and a 412 that
    are written twice are a 428 and a 412 that eventually disagree.
    """
    identity = getattr(entity, "precondition_identity", None)
    return dict(identity) if identity is not None else {"experiment_id": entity.id}


def _precondition_required(exp) -> JSONResponse:
    return JSONResponse(
        status_code=428,
        content={"error": "precondition_required", **_precondition_identity(exp)},
    )


def _malformed_if_match(exp) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": "malformed_if_match",
            **_precondition_identity(exp),
            "message": "If-Match must be one or more strong quoted validators.",
        },
    )


def _stale_write(exp, expected_token: str | None) -> JSONResponse:
    resp = JSONResponse(
        status_code=412,
        content={
            "error": "stale_write",
            **_precondition_identity(exp),
            "expected_rev": _expected_rev_from_token(expected_token),
            "current_rev": exp.rev,
            "expected_version": expected_token,
            "current_version": exp.version_token(),
        },
    )
    # Echo the CURRENT strong validator so the client can refresh in one hop.
    resp.headers["ETag"] = exp.etag()
    return resp


def _first_client_token(if_match: str | None) -> str | None:
    """The client's first strong validator, UNQUOTED — or ``None``.

    Exists so the durable-conflict 412 echoes ``expected_version`` /
    ``expected_rev`` in exactly the form ``_check_if_match`` echoes them (it passes
    ``tags[0][1:-1]``). Passing the RAW header instead silently produced
    ``expected_rev: null``, because the trailing quote makes the integer parse fail
    — two bodies for one condition, differing only where a client would look.

    No re-validation: by the time this is reachable the header has already been
    accepted. ``*`` carries no version and yields ``None``, which is the honest
    answer rather than a fabricated one.
    """
    if not if_match:
        return None
    first = next((t for t in (part.strip() for part in if_match.split(",")) if t), None)
    if not first or not _STRONG_TAG_RE.match(first):
        return None
    return first[1:-1]


def _save_versioned(exp, if_match: str | None) -> tuple[bool, JSONResponse | None]:
    """``exp.save_versioned()``, with a refused DURABLE write rendered as the 412.

    Returns ``(changed, None)`` normally, or ``(False, <412 response>)`` when the
    application's own database refused the write because the stored document had
    moved on.

    WHY THE SAME 412 AND NOT A NEW STATUS. ``_check_if_match`` above and this are
    the same contract enforced at two different distances. The header check asks
    "does the version this client holds match the copy THIS PROCESS just read"; the
    durable compare-and-swap asks "…and is that copy still the current one for
    every process". A client cannot act on the difference — the remedy is identical
    (re-read, re-apply, retry) — so inventing a second status code would only make
    two names for one condition. The response body and the echoed ETag are
    unchanged.

    THAT "THE REMEDY IS IDENTICAL" IS A CLAIM ABOUT THE STORE, NOT A TURN OF
    PHRASE, and it is only true because ``Experiment.save`` makes it true. A
    refused durable write adopts the winner's document into the workspace file
    before it re-raises; without that, a re-read would return the SAME stale local
    copy, the retry would offer the SAME already-taken rev, and the 412 would
    repeat forever. Re-read → re-apply → retry converges in one extra round trip
    because of that adoption. See ``ws.Experiment._adopt_winner_locally``.

    THE ECHOED VERSION COMES FROM THE WINNER, NOT FROM US.
    ``conflict.current_experiment`` prefers the document the database actually
    holds, read back inside the transaction that refused the write. Passing ``exp``
    would echo the losing write's own version, which exists nowhere and which a
    client re-reading would never see.

    WHAT WAS AND WAS NOT WRITTEN, STATED PER LAYER — this used to say "NOTHING WAS
    WRITTEN", unconditionally, and it was wrong at one of the three call sites.

    * The DATABASE took nothing: the durable write is what was refused.
    * This experiment's STATE was not applied. The durable write goes before the
      workspace file (``Experiment.save``), so the client's version never lands;
      ``save_versioned`` rolls its in-memory rev/``updated_utc`` bump back, and the
      handler's other in-memory mutations to ``exp`` are discarded with the
      request. The workspace file IS rewritten whenever the winner's row could be
      read and loaded — with the WINNER's document, which is the adoption above
      and never this client's change.
    * SIDE EFFECTS EARLIER IN THE HANDLER STAND. ``post_export`` writes the
      official record and its evidence sidecar (``_write_record``) BEFORE calling
      this, and those two files remain on disk. That is the half-written shape a
      fault between the two writes already produces, and the one the export
      handler's own reconciliation branch repairs on the next export — see the
      comment at that call site, which is the authority on this path.
    """
    try:
        return exp.save_versioned(), None
    except experiment_repository.DurableWriteConflict as conflict:
        return False, _stale_write(
            conflict.current_experiment(exp), _first_client_token(if_match)
        )


def _check_if_match(if_match: str | None, exp) -> JSONResponse | None:
    """Classify an ``If-Match`` header against the loaded experiment.

    Returns an error ``JSONResponse`` to short-circuit, or ``None`` to proceed:
      * absent      -> 428 precondition_required (grace retired; always enforced).
      * ``*``       -> None (matches iff the resource exists — and we loaded it).
      * strong match-> None (proceed).
      * weak/malformed/empty-list -> 400 (whole header malformed).
      * all valid strong validators but none match -> 412 stale_write.
    """
    if if_match is None:
        if vc.precondition_required():
            return _precondition_required(exp)
        return None
    raw = if_match.strip()
    if raw == "*":
        return None  # matches iff the resource exists — and we loaded it
    # RFC 9110 #-list: recipients ignore empty list elements, so a trailing comma
    # or an empty element is tolerated. A header that reduces to NO tags (e.g. just
    # "," or whitespace) is malformed.
    tags = [t for t in (part.strip() for part in raw.split(",")) if t]
    if not tags:
        return _malformed_if_match(exp)
    for tag in tags:
        if tag.startswith("W/") or not _STRONG_TAG_RE.match(tag):
            return _malformed_if_match(exp)
    if any(tag == exp.etag() for tag in tags):
        return None
    # All valid strong validators, none matched -> stale. Report the client's first.
    first_token = tags[0][1:-1] if tags else None
    return _stale_write(exp, first_token)


def _if_none_match_hit(if_none_match: str | None, exp) -> bool:
    """True if the client's If-None-Match indicates the record is UNCHANGED (→304).

    RFC 9110 uses weak comparison for If-None-Match; our validators are strong and
    the client echoes them verbatim, so normalise a leading ``W/`` then string-match.
    ``*`` matches iff the resource exists (it does here). Absent/empty/no-match → not
    a hit (fall through to the full 200 bundle).
    """
    if not if_none_match:
        return False
    raw = if_none_match.strip()
    if raw == "*":
        return True
    current = exp.etag()
    for part in raw.split(","):
        tag = part.strip()
        if tag.startswith("W/"):
            tag = tag[2:]
        if tag == current:
            return True
    return False


# --- summary / detail serialization -------------------------------------------


def _export_step_detail(result) -> str:
    """The ``export_draft`` pipeline step's `detail`, WITHOUT claiming a verdict nobody rendered.

    THE DEFECT THIS CLOSES. The line was::

        f"official schema valid: {result.official_report.ok if result.official_report else False}"

    ``ExportResult.official_report`` is ``None`` on exactly two paths that return BEFORE
    ``validate_official`` is ever called (``isaac_records/export.py``): the no-guessing
    draft failure, and ISAAC's anchored-pattern EXACTNESS gate, whose findings are folded
    into ``draft_report`` on the way out. On both of them the ternary's ``else`` branch
    rendered **"official schema valid: False"** — a verdict attributed to a document that
    never examined the record.

    That is not a wording nit here. ``CLAUDE.md`` §1 makes the vendored schema
    upstream-owned, and §12 states the rule directly: *"the gate is ISAAC's, not
    upstream's ... no surface may report an exactness refusal as an official-schema
    error."* §12 also records that a surface shipped exactly this conflation once already
    (``VerdictCard``, "Invalid against official ISAAC schema v1.05 — 0 errors" above
    ``schema_ok: true``). This was the same claim in the SERVER's own words, which is why
    no frontend fix could reach it: ``StagedRunner`` renders ``detail`` verbatim, and its
    own docstring quotes this exact string as the text a failing step shows.

    THE VOCABULARY IS NOT NEW. Three surfaces already faced the same missing
    discriminator on the analogous per-run payload and settled it the same way — name the
    official ISAAC schema ONLY where the verdict came from ``validate_official``, and
    otherwise report the finding count without naming a source
    (``ValidateReview.tsx``'s *"findings on this candidate record — source not named"``,
    ``RunFindings.tsx``'s ``fail`` clause reading "did not pass" rather than "failed the
    official ISAAC schema"). This is that wording, server-side. Inventing a fourth
    phrasing for one more instance of one condition is how a client ends up branching on
    prose.

    THE DISCRIMINATOR IS ``official_report is not None`` — the same one those surfaces
    use — and NOT ``result.ok``. A present report that says ``False`` is a real official
    schema verdict and keeps the original sentence verbatim, including its Python-cased
    ``False``, which ``StagedRunner``'s docstring and the frontend fixtures quote.

    The refused-early branch does NOT try to say WHICH gate refused, and that is
    deliberate rather than lazy: ``export.py`` folds exactness findings into
    ``draft_report`` alongside the no-guessing ones and the ``record_id`` check, so the
    wire this function reads carries no discriminator between them. Naming one would be
    guessing which — the same defect, one level finer.
    """
    if result.official_report is not None:
        return f"official schema valid: {result.official_report.ok}"
    n = len(result.draft_report.errors)
    return (
        f"refused before official validation — {n} finding"
        f"{'' if n == 1 else 's'} on the candidate record; source not named"
    )


def _summary(
    exp: Experiment,
    *,
    units: list[ExportUnit] | None = None,
    dry_run_ok: bool | None = None,
) -> dict:
    """One summary row. ``units`` is an already-composed ``export_units()`` list, used
    only by ``status()`` and only on its dry-run branch — see :func:`_shared_units`.
    ``dry_run_ok`` is the verdict OF that dry run, already derived by the caller for
    this same response — see :func:`_shared_dry_run`."""
    return {
        "id": exp.id,
        "title": exp.title,
        # P-pre-dean — the DERIVED scenario label for the five canonical synthetic
        # seeds (``None`` for any user-created record). Computed here from the id
        # alone; never stored on the experiment, never part of a draft/record/
        # sidecar/export. It names the SEEDED FIXTURE AT MATERIALISATION TIME and is
        # deliberately never refreshed, so it is worded in the past tense — a later
        # mutation changes the derived `status` below without falsifying the label.
        # (Invariance alone would NOT be enough: an invariant present-tense state
        # description over a mutating record is guaranteed to go false.)
        "scenario": ws.scenario_label(exp.id),
        "status": exp.status(units=units, dry_run_ok=dry_run_ok),
        "created_utc": exp.created_utc,
        "pending_count": exp.pending_count(),
        # KNOWN LIMIT, disclosed rather than fixed here (review item, and the C9
        # cost note in this module's export section): `evidenced_field_count` reads
        # `exp.draft` alone, so for a fan-out it counts the EXPERIMENT-LEVEL fields
        # only and is therefore lower than for a zero-run experiment holding the
        # byte-equivalent content (measured: 14 vs 26). It is not made run-aware
        # here because "how many evidenced fields does an experiment have" has no
        # single answer once N runs each resolve the same inherited field — summing
        # would multiply-count inheritance and reporting the maximum would be
        # arbitrary. It is a summary count, not a verdict, and nothing gates on it.
        "evidenced_field_count": exp.evidenced_field_count(),
        # REVIEW ITEM C5 — `all_units_exported()`, not `exported()`. For an
        # experiment with no runs these are the same function of the same field, so
        # the common case does not move. For a fan-out, `Experiment.record_id` stays
        # None forever, so `exported()` answered a permanent, and false, "no".
        "exported": exp.all_units_exported(),
        # …while `record_id` stays exactly what it is: null for a fan-out, because
        # there is no single record id. `exported` and `record_id` are now answering
        # two different questions rather than one question twice.
        "record_id": exp.record_id,
    }


#: Why a fan-out's singular ``artifact_refs`` are null. REVIEW ITEM C5: they used to
#: be null because ``exp.exported()`` was False, which reads as "nothing was
#: exported" — the same nulls a never-exported record produces. They are null because
#: the field is SINGULAR and this record has several, which is a different statement
#: and now says so.
#:
#: THE SECOND SENTENCE USED TO READ "Use the artifacts operation for the per-run
#: files." It is served BY the artifacts operation, which returns four nulls and this
#: same sentence — so it directed a reader in a circle, and the operation's own
#: OpenAPI description already said the opposite ("Those per-run files are not listed
#: here yet"). Found while rendering this string on the export screen, where a false
#: instruction becomes a visible dead end. The export response's ``records[]`` is the
#: one place the per-run filenames exist, and the sentence now says only that.
FAN_OUT_ARTIFACT_REASON = (
    "This record's runs each export their own official record, so there is no "
    "single record file. The export response lists each run's record and sidecar "
    "filename; no read operation lists them yet."
)


def _shared_units(exp: Experiment) -> list[ExportUnit]:
    """The ONE composed unit list a single detail response is built from.

    **THE MEASURED DEFECT THIS CLOSES.** ``GET /api/experiments/{id}`` is flat in payload
    (~1.5 KB at any run count) and was linear in TIME — 3.0 ms at 25 runs, 83.2 ms at
    1,000 (`docs/evidence/scale-envelope-2026-08-25.md` §3). ``cProfile`` put
    ``copy.deepcopy`` at ~49% cumulative, driven by ``Experiment.resolved_run_draft`` at
    **3,000 calls on a 1,000-run record** — exactly 3x the run count, because
    ``export_units()`` composes every run's draft and :func:`_detail` reached it three
    times: ``_workflow_for`` -> ``draft_ok``, the response's own ``draft_ok``, and
    ``dependencies.artifact_state`` -> ``_fan_out_artifact_state``. On a record with no
    open questions it is FIVE, because ``status()`` and ``export_ready()`` stop
    short-circuiting past ``_all_units_pass_dry_run``. Document parsing was never the
    cost: ``json.decoder.raw_decode`` was 1 call per request.

    **THREADED, NOT MEMOISED, AND THIS FUNCTION IS THE SEAM RATHER THAN A CACHE.** A
    per-instance memo would be unsafe: this module mutates an ``Experiment`` and then
    re-reads its derived state in the same request (answer -> recompute status/workflow),
    so a ``cached_property`` or an instance dict would serve a stale composition after a
    write. This composes once per RESPONSE, hands the list to each consumer as an
    argument, and stores nothing anywhere. Every consumer's ``units=None`` default is
    still the code that ran before, which is what lets
    ``test_detail_route_composes_each_run_once.py`` reproduce the pre-change path by
    patching this one function to return ``None`` and compare the two responses byte for
    byte.

    Composing it here is safe because :func:`_detail` WRITES NOTHING between the
    composition and the last consumer of it, and because the three consumers read their
    drafts without writing them (``validate_draft``, ``export_draft`` and ``transform``
    all build a new object) — asserted, not assumed, by that file's no-mutation test.
    A zero-run experiment gets a list too: its single unit carries ``exp.draft`` ITSELF
    rather than a composition, so there is nothing to save on the composition.
    ~~"and one ``export_units()`` call to save on the dry run"~~ — **TRUE ONLY WHEN THE
    RECORD HAS NO OPEN QUESTIONS, and corrected in place because as written it claimed a
    saving on the common case.** Measured over the HTTP surface on a zero-run record,
    ``export_units`` calls per detail read, un-threaded -> threaded:

    * ``pending_count() > 0``: **0 -> 1**. The dry run is never reached (``status()``
      short-circuits on pending and ``export_ready()`` returns before it), so this
      function strictly ADDS one call. It is a cheap one — a zero-run unit list is one
      unit wrapping ``exp.draft`` with nothing composed — and the read still nets a
      saving in the work that matters: ``validate_draft`` goes 2 -> 1, because
      ``draft_ok`` is now derived once for the whole response.
    * ``pending_count() == 0``: **2 -> 1**, which is the saving the struck sentence
      described.
    """
    return exp.export_units()


def _shared_dry_run(exp: Experiment, *, units: list[ExportUnit] | None) -> bool | None:
    """The ONE dry-run verdict a single detail response is built from, or ``None``.

    **THE RESIDUAL :func:`_shared_units` DID NOT REMOVE, AND ON THE WORST WORKLOAD IT WAS
    THE DOMINANT ONE.** Sharing the composed unit list removed the repeated
    *composition*; it left the repeated *dry run*, because ``status()`` and
    ``export_ready()`` each call ``Experiment._all_units_pass_dry_run`` independently.
    Measured over HTTP on a **fully answered, unexported 200-run** record — the workload
    the scale envelope calls *"the worst case and the one a scientist reaches at the END
    of the work"* — ``export_draft`` was **400 calls per request, exactly 2x the run
    count**, unmoved by the composition threading (1,000 -> 200 ``resolved_run_draft``,
    5 -> 1 ``export_units``, 400 -> 200 ``validate_draft``, **400 -> 400
    ``export_draft``**). An independent review put that at roughly HALF the request
    against ~3% for the composition, which is why the fully-answered gain was ~1.28x and
    not the 2.4x headline. This seam is what closes it.

    **IT MUST NOT MAKE THE DRY RUN HAPPEN WHERE IT DOES NOT HAPPEN TODAY**, and that is
    the trap a naive "compute it once up front" walks into. On a record that still owes
    questions — the COMMON case, and the one every §1/§2 table in the scale envelope was
    taken on — both consumers short-circuit before the dry run, so it is entered ZERO
    times. Eager computation would turn 0 into 1 and make the common read slower to
    speed up the rare one. ``Experiment.dry_run_verdict`` therefore gates on
    ``pending_count() > 0`` and answers ``None``, which is the union of the two
    short-circuits; see its docstring for why that union is exact.

    **THREADED, NOT MEMOISED**, for the reason :func:`_shared_units` sets out at length:
    this module mutates an ``Experiment`` and re-reads its derived state in the same
    request, so anything stored on the instance can be served stale. Nothing is stored.
    ``None`` means "derive your own" to every consumer, exactly as ``units=None`` does,
    which is what lets ``test_detail_route_composes_each_run_once.py`` reproduce the
    pre-change path by patching this one function.

    THE ONE COST, MEASURED HERE RATHER THAN QUOTED FROM ELSEWHERE: this adds a fifth
    ``pending_count()`` call to a detail read that already made four, and it is paid on
    EVERY read including the pending ones that gain nothing from the sharing. Timed
    directly over 2,000 repetitions: **0.0195 ms at 200 runs, 0.0474 ms at 500** — about
    0.26% of the ~18 ms that read takes at 500 runs, and inside the run-to-run spread of
    the A/B, which measured 17.1 -> 17.3 ms minimum over 41 interleaved reps. It is named
    here rather than left for a reader to find.
    """
    return exp.dry_run_verdict(units=units)


def _detail(exp: Experiment) -> dict:
    # ONE COMPOSITION FOR THE WHOLE RESPONSE — see `_shared_units` for the measurement
    # and for why this is an argument rather than a cache.
    units = _shared_units(exp)
    # …AND ONE DRY RUN. `status()` and `export_ready()` each dry-ran every unit, which
    # is `export_draft` over 2x the run count on a fully answered record and roughly
    # half the request — the largest single thing the unit-list threading did NOT
    # remove. `None` when neither would have reached it; see `_shared_dry_run`.
    dry_run_ok = _shared_dry_run(exp, units=units)
    detail = _summary(exp, units=units, dry_run_ok=dry_run_ok)
    record_path = exp.record_path()
    sidecar_path = exp.sidecar_path()
    # `_workflow_for` is the ONE derivation (review item C5). It used to be inlined
    # here with `exported=exp.exported()` while `_workflow_for` — used by every
    # mutation response — passed `all_units_exported()`, so a fully-exported fan-out
    # got `export: 'completed'` from the export response and `export: 'current'` from
    # the very next detail GET.
    # AND ONE `draft_ok` FOR THE WHOLE RESPONSE. Sharing the unit list stopped the
    # RE-COMPOSITION, but `draft_ok` was still being DERIVED twice from it — once for
    # the workflow's `complete_metadata`/`review_evidence` steps and once for the
    # response's own key — which is `validate_draft` over every unit, twice. Measured
    # on a 1,000-run record: 2,000 `validate_draft` calls per request, exactly 2x runs.
    # It is the same experiment at the same revision in the same read, so the second
    # derivation could only ever agree with the first.
    draft_ok = exp.draft_ok(units=units)
    workflow = _workflow_for(exp, units=units, draft_ok=draft_ok, dry_run_ok=dry_run_ok)
    fan_out = bool(exp.runs)
    artifact_refs = {
        "record_filename": record_path.name if exp.exported() and record_path else None,
        "sidecar_filename": sidecar_path.name if exp.exported() and sidecar_path else None,
    }
    if fan_out:
        artifact_refs["reason"] = FAN_OUT_ARTIFACT_REASON
    detail.update(
        {
            "draft_ok": draft_ok,
            # P30.6 — SAFE basename only, never the absolute server/mount path
            # (CLAUDE.md path-boundary rules). The client labels + names the
            # download from the filename; JSON content comes from /artifacts.
            "artifact_refs": artifact_refs,
            "source_files": (exp.source or {}).get("files") or [],
            "workflow": workflow,
            # Derived exported-artifact freshness (P28.2): none | current | stale.
            "artifact": dependencies.artifact_state(exp, units=units),
        }
    )
    return detail


def _workflow_for(
    exp: Experiment,
    *,
    units: list[ExportUnit] | None = None,
    draft_ok: bool | None = None,
    dry_run_ok: bool | None = None,
) -> dict:
    """Derive the workflow from an experiment's current signals (same call as
    ``_detail``). Used to capture the pre-mutation step states and to surface the
    post-mutation workflow on a mutation response.

    ``exported`` is ``all_units_exported()``, not ``exported()``. The workflow's
    final step asks "has this record been exported", and under contract §1 D1 an
    experiment with runs is exported when every run is — ``Experiment.record_id``
    stays ``None`` for such an experiment, so ``exported()`` would report the step
    unsatisfied forever. For an experiment with no runs the two are the same
    function of the same field, so nothing about today's behaviour moves.

    ``units`` AND ``draft_ok`` ARE OPTIONAL, AND THEY ARE OPTIONAL BECAUSE OF THE BLAST
    RADIUS. This function is called by EVERY mutation response as well as by
    :func:`_detail` — **fifteen call sites in this module, counted rather than estimated
    (``grep -n '_workflow_for(' routes.py``); the commit that introduced the parameters
    said "a dozen" and that was wrong by three** — and each of the other fourteen has
    exactly one derivation to make and nothing to share it with. So they are untouched
    and keep deriving their own; only :func:`_detail`, which needs four unit-dependent
    facts for one response, passes anything. See :func:`_shared_units`.

    ``draft_ok`` is a BOOLEAN THE CALLER ALREADY DERIVED, not a way to assert one. It is
    only ever passed the value ``exp.draft_ok(units=units)`` returned for this same
    experiment at this same revision inside the same read — pinned by
    ``test_detail_route_composes_each_run_once.py``, which compares the whole response
    against the un-threaded derivation byte for byte. It is deliberately NOT plumbed
    through to any route that could take it from a request.

    ``dry_run_ok`` IS THE SAME KIND OF THING AS ``draft_ok`` AND CARRIES THE SAME RULE.
    It is the verdict ``Experiment.dry_run_verdict`` returned for this experiment at
    this revision in this read, threaded so that ``export_ready()`` here and
    ``status()`` in :func:`_summary` share ONE dry run instead of performing one each —
    ``export_draft`` over 2x the run count on a fully answered record, and the single
    largest cost the unit-list threading left behind (:func:`_shared_dry_run`). ``None``
    means "derive your own", which is what the other fourteen call sites do and what the
    consumers themselves do when they reach the dry-run branch at all. Like
    ``draft_ok``, it is not plumbed through to any route that could take it from a
    request.
    """
    return derive_workflow(
        pending_count=exp.pending_count(),
        draft_ok=exp.draft_ok(units=units) if draft_ok is None else draft_ok,
        ready=exp.export_ready(units=units, dry_run_ok=dry_run_ok),
        exported=exp.all_units_exported(),
        rev=exp.rev,
    )


# --- defensive artifact reads (shared) ----------------------------------------


def _read_artifact_json(path) -> dict | None:
    """Parse one exported artifact file, or ``None`` when it is absent/unreadable/not JSON.

    P4. A read operation must never 500. An unguarded read raised ``FileNotFoundError``,
    i.e. an unhandled exception on a GET, which is a 500 for two separate reasons:
    the caller gets nothing usable (and, in a bundled ``Promise.all``, neither do its
    siblings), and the exception message — which carries the ABSOLUTE server path
    ``/data/isaac-workspace/…`` — is written to the SERVER LOG, itself an
    exfiltration surface (P30.6). To be exact, and this was overstated once already:
    the RESPONSE body is the framework's bare ``Internal Server Error``
    (``app.debug`` is False and no 500 handler is registered), so the path never
    reached a client. So an unreadable artifact becomes a typed, path-free absence
    here rather than an exception every caller has to survive. Same tolerance as
    ``dependencies.artifact_state``, which already treats this situation as ``stale``
    instead of throwing.

    SHARED by every reader of an exported artifact: ``post_validate``,
    ``_warnings_payload``, ``get_evidence``, ``get_artifacts`` and
    ``_assistant_validate_dryrun``. Each decides for itself what a ``None`` means in
    its own contract; the tolerance itself has exactly one definition.

    The ``except`` is deliberately NARROW. ``OSError`` covers absent/unreadable/
    permission/is-a-directory; ``ValueError`` covers ``json.JSONDecodeError``. Any
    OTHER exception type propagates on purpose: a ``MemoryError``, a
    ``KeyboardInterrupt``, or a genuine programming error must NOT be silently
    reported to the caller as "the artifact is missing", because that would be a
    false statement about the filesystem. Pinned by
    ``test_export_recovery.test_read_artifact_json_lets_an_unexpected_exception_propagate``.
    (``dependencies.artifact_state`` uses a bare ``except Exception`` for the same
    read — the codebase is inconsistent here. That is left alone on purpose: it is a
    different function with a different contract (it must produce a state label, never
    raise) and changing it is not this slice's scope.)
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # ValueError covers json.JSONDecodeError
        return None


# --- 1. health ----------------------------------------------------------------


def _build_commit() -> str | None:
    """Deploy identity, read live (not cached) so it reflects the running env.

    ``ISAAC_BUILD_COMMIT`` takes precedence when set; else Railway's
    auto-injected ``RAILWAY_GIT_COMMIT_SHA``; else ``None`` — never guessed.
    """
    return (
        os.environ.get("ISAAC_BUILD_COMMIT", "").strip()
        or os.environ.get("RAILWAY_GIT_COMMIT_SHA", "").strip()
        or None
    )


@router.get(
    "/health",
    tags=[TAG_META],
    summary="Report Liveness and Deploy Identity",
    description=(
        "Liveness banner for platform and container probes: the service status, "
        "the runtime data mode, the name of the deterministic core package the "
        "app calls in process, the app version, and the build commit when the "
        "deployment supplies one (otherwise `null` — it is never guessed). This "
        "is the one operation that stays reachable without credentials when the "
        "deployment enables authentication. Read-only.\n\n"
        "It also states whether this deployment has an application database "
        "configured, how that database is classified, whether hosted display of "
        "its per-record content is open, and the outcome of the most recent "
        "reconnaissance scan in this process. That block is derived from "
        "configuration alone: this operation never opens a database connection, "
        "issues a query, or waits on one, so a database problem can never change "
        "its result and can never fail a container probe.\n\n"
        # THIS PARAGRAPH USED TO END "That is derived from configuration alone as
        # well, so it says how this deployment is set up, never that a database is
        # reachable right now." It was true of the code as first written and it was
        # the sentence that made the defect invisible: a pod whose experiments
        # table did not exist reported `durable: true` while every read and write
        # against it failed. `experiment_storage` now also reports an observation,
        # so the disclaimer is corrected rather than kept as a comforting one.
        "It states, in `experiment_storage`, whether an experiment created here is "
        "stored durably, stored only for as long as this server runs, or not being "
        "stored at all because a database this deployment is configured to use is "
        "not answering. The first two are read from configuration. The third is an "
        "observation, recorded when a real read or write against that database "
        "failed — so this operation still opens no connection of its own, and it "
        "reports what has already happened rather than testing anything now.\n\n"
        "It states, in `submission`, whether this deployment is configured to accept "
        "a submission at all, and if not, why — submitting needs both durable "
        "storage and a way to establish who is calling, and a deployment can have "
        "one without the other. `configuration_permits` is named for what it is: "
        "configuration is all this operation looked at, so it never promises the "
        "write would land. It also reports the basis on which an author would be "
        "recorded, so a deployment attributing on a test-fixture basis says so here "
        "rather than only in its manifest."
    ),
    response_description="The liveness banner.",
)
def health() -> dict:
    # The two helpers and two constants below are defined with the
    # reconnaissance operation (section 22); they are resolved at call time.
    # ZERO I/O in the database block. Reading the feature switch is an
    # environment read and the last-scan summary is an in-process dict; nothing
    # here connects, queries, or blocks. This operation is the container
    # readiness-probe target, so a database that is down, slow, or misconfigured
    # must not be able to influence its status code or its body's `status`.
    configured = _db_recon_configured()
    return {
        "status": "ok",
        "mode": runtime_mode.runtime_mode(),
        "core": "isaac_records",
        "version": __version__,
        "commit": _build_commit(),
        "database": {
            "configured": configured,
            "classification": _DB_RECON_CLASSIFICATION if configured else None,
            "contains_production_derived_records": True if configured else None,
            "record_display": _DB_RECON_RECORD_DISPLAY,
            "last_recon": _db_recon_last_summary(),
        },
        # DELIBERATELY ADJACENT TO `database`, AND DELIBERATELY NOT PART OF IT.
        # They answer different questions and conflating them would be the kind of
        # error this file has made before: `database` is about the READ-ONLY
        # diagnostic over the production-derived sample, which stays closed for
        # per-record display; `experiment_storage` is about where THIS
        # APPLICATION'S OWN experiments are stored. A deployment can have the
        # second without the first ever being scanned.
        "experiment_storage": experiment_repository.storage_status(),
        # A THIRD BLOCK, ADJACENT TO THE OTHER TWO AND DELIBERATELY NOT PART OF
        # EITHER. `database` is about the read-only diagnostic over the
        # production-derived sample; `experiment_storage` is about where this
        # application's own experiments are stored; this is about whether a
        # SUBMISSION — a durable, attributable declaration — can be recorded at all.
        # A deployment can have durable storage and still be unable to submit,
        # because submitting additionally requires an attributable person and the
        # 0003/0004 tables.
        #
        # ZERO I/O, exactly like the two above: `capability` reads configuration and
        # the resolved verifier and opens nothing. Its field is called
        # `configuration_permits` rather than `available` for that reason — whether
        # the tables exist cannot be known without a connection, and claiming
        # availability from configuration alone is the precise defect
        # `experiment_storage` was corrected for.
        "submission": submission_store.capability(),
    }


# --- 1b. worked-example sessions ----------------------------------------------
#
# The five built-in example records live ONLY inside a worked-example session, one
# independent copy per session. The ordinary workspace is never seeded with them.
# The filesystem is the session registry (see ``workspace``'s module docstring), so
# these two operations are the whole lifecycle: create and discard. Expiry is swept
# at create time rather than by a background task, so there is nothing to keep
# running and nothing to lose on a restart.


@router.post(
    "/tutorial/sessions",
    status_code=201,
    tags=[TAG_TUTORIAL],
    summary="Open a Worked-Example Session",
    description=(
        "Creates an isolated worked-example workspace containing the five built-in "
        "example records, and returns its id together with the record ids actually "
        "materialised in it. Send that id as the `X-Isaac-Tutorial-Session` header on "
        "the record and example-workspace operations to work inside the session.\n\n"
        "The examples exist only inside a session: the ordinary workspace contains "
        "none of them, and nothing here writes to it. Two sessions are completely "
        "independent — the same example record can be answered, edited and exported "
        "in one without being visible from the other.\n\n"
        "The returned record ids are read back from the session that was just "
        "created, so they state what is there rather than what was intended. Each "
        "session expires after the reported number of hours; expired sessions are "
        "cleaned up whenever a new one is opened."
    ),
    response_description=(
        "The new session's id, the record ids materialised in it, and how many hours "
        "it survives."
    ),
    responses={**_R_UNAUTHORIZED},
)
def create_tutorial_session() -> dict:
    # Sweep FIRST, so expired sessions are retired by ordinary use rather than by a
    # background task that could die silently. Bounded and idempotent; it can only
    # ever remove directories inside the worked-example namespace.
    ws.sweep_stale_tutorial_sessions()
    session_id, record_ids = ws.create_tutorial_session()
    return {
        "session_id": session_id,
        "record_ids": record_ids,
        "ttl_hours": ws.TUTORIAL_TTL_HOURS,
    }


#: The path parameter naming a worked-example session.
TutorialSessionId = Annotated[
    str,
    Path(
        description=(
            "The id of a worked-example session, as returned by "
            "`POST /api/tutorial/sessions`."
        )
    ),
]


@router.delete(
    "/tutorial/sessions/{session_id}",
    status_code=204,
    tags=[TAG_TUTORIAL],
    summary="Discard a Worked-Example Session",
    description=(
        "Discards a worked-example session and everything in it, including any "
        "answers, edits and exported artifacts produced inside it. Nothing outside "
        "the session is touched.\n\n"
        "Discarding a session that no longer exists succeeds: the outcome the caller "
        "asked for — that this session is gone — already holds, so repeating the "
        "request is safe and a client never has to know whether it is retrying. A "
        "malformed id is rejected instead, because it names no session at all."
    ),
    response_description="The session does not exist. No body.",
    responses={
        **_R_UNAUTHORIZED,
        204: {"description": "The session does not exist. No body."},
    },
)
def delete_tutorial_session(session_id: TutorialSessionId) -> Response:
    # Malformed -> 422 (it names no session). Absent -> 204, deliberately the same as
    # an existing session, because the POSTCONDITION is identical in both cases.
    if not ws.is_tutorial_session_id(session_id):
        raise TutorialScopeError(
            422,
            {
                "error": "invalid_tutorial_session",
                "message": (
                    "The worked-example session id is not of the expected form, so "
                    "it names no session. Nothing was removed."
                ),
            },
        )
    ws.dispose_tutorial_session(session_id)
    return Response(status_code=204)


# --- 2. demo run --------------------------------------------------------------

#: Refusal payload for an example-workspace operation invoked outside a session.
#: These two operations act on the built-in example records, and those exist only
#: inside a worked-example session, so there is nothing for them to act on in the
#: ordinary workspace. Refusing is not a policy preference: without the header the
#: canonical target does not exist, and the alternative to a typed refusal is a
#: misleading drift/classification verdict about records that are simply absent.
_TUTORIAL_REQUIRED_MESSAGE = (
    "This operation works on the built-in example records, which exist only inside "
    "a worked-example session. Open one with POST /api/tutorial/sessions and send "
    "its id as the X-Isaac-Tutorial-Session header. Nothing was written."
)


def _tutorial_scope_required(operation: str) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": "tutorial_scope_required",
            "operation": operation,
            "header": TUTORIAL_SESSION_HEADER,
            "message": _TUTORIAL_REQUIRED_MESSAGE,
        },
    )


def _demo_baseline(target_id: str) -> Experiment | None:
    """The canonical seed baseline for a demo target, built IN MEMORY only.

    Returns ``None`` when ``target_id`` is not a canonical seed id. The lookup used
    to be a bare ``next(...)`` over ``_seed_specs()``, which raises ``StopIteration``
    for an unknown id — inside a sync handler that surfaces as an HTTP 500 with a
    traceback in the server log, rather than as a refusal the caller can act on. The
    two current call sites pass a server-derived id and so cannot trip it; the
    default is here so a future caller cannot turn a lookup miss into a 500.

    This is the exact authoritative state ``ensure_tutorial_seeded`` materialises for
    ``target_id`` — the same ``_SeedSpec`` row, the same source, the same draft
    function — reconstructed here purely so its authoritative signature can be
    compared against what is actually on disk. It is NEVER saved, so building it
    writes nothing and touches no ``rev``, ``generation`` or ``updated_utc``.

    ``record_id`` matters and is easy to get wrong: an ``exported`` spec is
    materialised through a real export keyed to the spec's own id, so disk
    carries ``record_id == spec.id``. A freshly *constructed* ``Experiment``
    carries ``record_id=None``, and ``record_id`` is inside
    ``_authoritative_signature`` — so a baseline that omitted it would report a
    spurious mismatch on every ``full``-mode run.

    The private ``ws`` helpers are used deliberately: ``_seed_specs`` /
    ``_seed_source`` are the single definition of the canonical baseline, and
    re-deriving either of them here would create a second, silently divergent
    copy of the seed's content.
    """
    spec = next((s for s in ws._seed_specs() if s.id == target_id), None)
    if spec is None:
        return None
    return Experiment(
        id=spec.id,
        title=spec.title,
        created_utc=spec.created_utc,
        source=ws._seed_source(),
        draft=spec.draft_fn(),
        record_id=spec.id if spec.exported else None,
    )


@router.post(
    "/demo/run",
    tags=[TAG_DEMO],
    summary="Run the Worked Example Pipeline",
    # THE HEADER REQUIREMENT BELONGS IN THE MAIN DESCRIPTION, not only in the `409`
    # sub-description. A reader consulting the operation to find out how to call it
    # would have seen no precondition at all, and only discovered the requirement by
    # reading the failure case they had not yet hit. The handler's own docstring has
    # always said so; the published contract now does too, first, because it is the
    # first thing true of every call.
    description=(
        "REQUIRES the `X-Isaac-Tutorial-Session` header. The built-in example "
        "records are created only inside a worked-example session, so without one "
        "there is nothing for this operation to run over: it refuses with `409` "
        "(`tutorial_scope_required`) and writes nothing. Everything below describes "
        "what it does inside the session that header names — it addresses no other "
        "scope, and it can neither read nor write a record in the ordinary "
        "workspace.\n\n"
        "Runs the committed worked-example pipeline and returns the ordered steps "
        "it executed together with the resulting experiment id and status. "
        "`mode: \"draft_only\"` (the default) extracts a draft from the committed "
        "reference files and runs the no-guessing draft checks; `mode: \"full\"` "
        "additionally applies the committed simulated answers and exports an "
        "official record. It targets one fixed canonical experiment id per mode, "
        "so re-running never adds a record and never increases that session's "
        "record count. It reads only the two committed reference files and accepts "
        "no uploaded data.\n\n"
        "It never overwrites your work. The target must still hold exactly its "
        "original example content: when it does, running the pipeline would "
        "reproduce that content byte for byte, so nothing at all is written and "
        "the record's version is untouched. If the target has been changed — an "
        "answer confirmed, a field edited, a record exported — the run is refused "
        "with `409` and nothing is written.\n\n"
        "A body other than `draft_only` or `full` for `mode` is rejected and "
        "nothing runs."
    ),
    response_description="The experiment id, the ordered pipeline steps, and the resulting status.",
    responses={
        **_R_UNAUTHORIZED,
        **_R_TUTORIAL_SCOPE,
        409: {
            "description": (
                "Refused without writing anything, for one of two reasons. Either no "
                "`X-Isaac-Tutorial-Session` header was sent — the built-in examples "
                "exist only inside a worked-example session, so outside one there is "
                "nothing for this operation to run over — or the canonical record "
                "this mode targets no longer holds its original content, so running "
                "the example over it would discard a real change. The typed `error` "
                "field distinguishes them: `tutorial_scope_required` or "
                "`demo_target_drifted`. Restore the built-in examples with "
                "`POST /api/demo/reset` if you want that content back."
            )
        },
    },
)
def demo_run(
    scope: TutorialScopeDep,
    body: dict = Body(
        default=None,
        description=(
            "Optional. `{\"mode\": \"draft_only\"}` (the default when the body is "
            "omitted) or `{\"mode\": \"full\"}`."
        ),
    ),
) -> dict:
    """Run the worked-example pipeline inside a worked-example session.

    REQUIRES tutorial scope. Called without ``X-Isaac-Tutorial-Session`` it refuses
    with ``409 {"error": "tutorial_scope_required"}`` and writes nothing. That is a
    correctness requirement, not only a policy one: this build cannot create the
    canonical target id in the ordinary workspace, so an unscoped run would either
    report a spurious ``demo_target_drifted`` about a record it has no way to
    materialise, or seed the ordinary workspace — and the whole point of this slice is
    that nothing seeds the ordinary workspace.
    """
    if scope is None:
        return _tutorial_scope_required("POST /api/demo/run")
    mode = (body or {}).get("mode", "draft_only")
    if mode not in ("draft_only", "full"):
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_mode", "allowed": ["draft_only", "full"]},
        )

    steps: list[dict] = []

    # Idempotent: ensure the canonical five-scenario seed exists first, then run
    # the requested pipeline against a FIXED canonical id rather than appending a
    # new random experiment. Re-running never increases the record count and
    # preserves canonical identities. It also never WRITES to that id — see the
    # precondition below.
    ws.ensure_tutorial_seeded(scope)
    target_id = ws.SEED_DONE_ID if mode == "full" else ws.SEED_NEW_DRAFT_ID

    # [1] build_draft — deterministic extraction from the synthetic fixtures.
    draft = build_draft(ws.CSV_PATH, ws.LISTING_PATH)
    steps.append(
        {
            "name": "build_draft",
            "detail": (
                f"{len(draft.get('fields') or {})} evidenced fields, "
                f"{len(draft.get('pending') or [])} pending blocker(s)"
            ),
            "ok": True,
        }
    )

    # [2] validate_draft — no-guessing checks (pass even with pending open).
    draft_report = validate_draft(draft)
    steps.append(
        {
            "name": "validate_draft",
            "detail": f"draft ok: {str(draft_report.ok).lower()}",
            "ok": draft_report.ok,
        }
    )

    # The read of the fixed canonical target id is serialised under the same
    # per-record lock the /answers and /export mutations use, and under the SAME
    # scope, so the drift check below cannot observe a half-applied concurrent
    # mutation. ensure_tutorial_seeded/build_draft/validate_draft above stay outside
    # the lock (the seeder only creates MISSING ids; neither racily mutates the
    # target's persisted state).
    with ws.record_lock(target_id, session_id=scope):
        # PRECONDITION — refuse, and never write (W1).
        #
        # This operation targets a fixed canonical id derived server-side from
        # `mode`, so the caller structurally cannot supply an If-Match for it, and
        # `ensure_tutorial_seeded()` above guarantees the record exists in this
        # session, which makes `If-Match: *` vacuous. Its precondition is therefore
        # expressed against
        # content, not against a token: the target must still hold exactly the
        # canonical seed state.
        #
        # When it does, running the pipeline would rewrite byte-identical content,
        # so the write is provably redundant and is SKIPPED ENTIRELY — no
        # create_experiment, no _write_record, no save(). That is what protects
        # `rev`, `generation`, `updated_utc` and `answer_log`: a write that never
        # happens cannot reset them, cannot drop an audit entry, and cannot mint
        # the same token over different content (the ABA the generation nonce
        # exists to prevent).
        #
        # When it does not, a real user change is present. Overwriting it would
        # destroy a confirmed edit and its audit trail, so the run is refused.
        #
        # ONE read, not two: the signature is computed from the record already
        # loaded here rather than re-parsing the state file through
        # ``_persisted_sig_and_rev``. That matters for honesty as much as cost —
        # the two disagree on a corrupt file (one swallows JSONDecodeError and
        # returns None, the other raises), and only one answer can be right.
        #
        # An ABSENT record refuses (defence in depth: ``ensure_tutorial_seeded``
        # above already heals a missing id in this session before the lock, so this
        # arm is not expected to fire — it is not, as an earlier note claimed,
        # protection against a concurrent ``demo_reset``, which takes the SAME
        # per-record lock for every canonical id). A CORRUPT state file surfaces as
        # a 500 from ``load_experiment``, exactly as it already does on every read
        # path; it is not silently treated as drift.
        #
        # A ``None`` baseline would mean ``target_id`` is not a canonical seed id.
        # ``target_id`` is chosen from ``mode`` two lines above, so it always is; the
        # arm is written defensively rather than left to raise.
        baseline = _demo_baseline(target_id)
        exp = ws.load_experiment(target_id, session_id=scope)
        if (
            baseline is None
            or exp is None
            or ws._authoritative_signature(exp) != ws._authoritative_signature(baseline)
        ):
            return JSONResponse(
                status_code=409,
                content={
                    "error": "demo_target_drifted",
                    "experiment_id": target_id,
                    "message": (
                        "This record has changed since it was created, so the "
                        "worked example will not run over it — nothing was "
                        "written and your work is intact. Use "
                        "POST /api/demo/reset to restore the built-in examples."
                    ),
                },
            )

        if mode == "full":
            # [3] apply_answers — the committed SIMULATED human answers, verbatim, so the
            #     completion path matches run_synthetic_demo.py exactly. Pure: it
            #     returns a completed draft and persists nothing.
            answers = ws.load_demo_answers()
            completed = apply_answers(draft, answers)
            steps.append(
                {
                    "name": "apply_answers",
                    "detail": (
                        f"{len(completed.get('pending') or [])} pending remaining, "
                        f"{len(completed.get('assets') or [])} assets resolved"
                    ),
                    "ok": True,
                }
            )

            # [4] export_draft — the schema-gated transform, run as a DRY RUN so the
            #     reported verdict is real. `_write_record` is deliberately not
            #     called: the seeded record and sidecar already on disk are the
            #     output of this same transform over this same draft.
            result = export_draft(completed, REPO_ROOT, record_id=target_id)
            steps.append(
                {
                    "name": "export_draft",
                    "detail": _export_step_detail(result),
                    "ok": result.ok,
                }
            )

    return {"experiment_id": exp.id, "steps": steps, "status": exp.status()}


# --- 2b. guarded example-workspace reset (P26.0b, precondition added in R1) ----
#
# Restores the workspace to EXACTLY the five canonical P26.0a scenarios. It never
# accepts caller-supplied ids or paths (unknown fields are rejected by the typed
# request model), removes ONLY managed records this workspace itself created, and
# refuses on any ambiguous record. There is deliberately NO general per-experiment
# delete route.
#
# R1 added the ``plan_digest`` precondition. Every guard here is FAIL-CLOSED and each
# has its own status code, because a UI that cannot tell the refusals apart cannot
# respond correctly to any of them:
#
#   403  not synthetic-only        — stop; nothing about this request can fix it
#   409  wrong/missing phrase      — the operator can fix it by typing correctly
#   409  ambiguous record present  — stop; a human must resolve the record first
#   428  digest omitted            — the client is broken; send the preview's digest
#   412  digest stale              — preview again and let the operator re-approve
#
# The 403/409 arms deliberately still classify (read-only) so the refusal carries the
# same counts as a preview would; none of them mutates anything.

#: The phrase an operator types to arm the destructive reset. It is DISPLAYED and
#: typed, so it is product copy as well as a wire value: it must be truthful and free
#: of harness jargon, and it must match `RESET_CONFIRMATION` in `apps/web/src/lib/api.ts`
#: character for character or every reset fails closed with a 409.
_RESET_CONFIRMATION = "RESET EXAMPLE WORKSPACE"

#: Why the reset declined, when it declined. A TYPED reason, because the five
#: refusals are not interchangeable and the UI must respond differently to each:
#: re-preview (stale digest), send the digest (omitted), fix the phrase, or stop
#: entirely (an ambiguous record, or the wrong runtime mode). ``None`` on success.
DemoResetRefusal = Literal[
    "not_synthetic_only",
    "confirmation_required",
    "plan_digest_required",
    "plan_digest_stale",
    "ambiguous_records_present",
]


class DemoResetRequest(BaseModel):
    """Typed reset request. ``extra="forbid"`` rejects any caller-supplied ids or
    paths (e.g. ``ids``/``experiment_id``/``path``) with a 422 — they can never
    influence what is removed."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["preview", "execute"]
    confirmation: str | None = None
    #: The ``plan_digest`` the matching ``preview`` returned. REQUIRED for
    #: ``execute``: it is the precondition that stops a dialog left open from
    #: executing a classification the operator approved but that no longer holds.
    #: Ignored for ``preview``, which mutates nothing and so has no precondition.
    plan_digest: str | None = None


class DemoResetResponse(BaseModel):
    """Typed, path-free reset result (no filesystem paths ever leak out)."""

    status: Literal["ok", "refused"]
    mode: Literal["preview", "execute"]
    #: ``None`` when ``status`` is ``ok``; otherwise which guard declined.
    refusal_reason: DemoResetRefusal | None = None
    previous_count: int
    canonical_count: int
    legacy_count: int
    ambiguous_count: int
    removed_count: int
    final_count: int
    canonical_ids: list[str]
    removable: list[dict]
    state_counts: dict
    #: An opaque digest of the classified workspace. Always the CURRENT one, so a
    #: stale-precondition refusal echoes the digest that would work — the client
    #: recovers in one hop, exactly as the ``If-Match`` 412 echoes the current ETag.
    plan_digest: str
    #: Derived counts of the confirmed work this reset would discard. Every number
    #: comes from persisted state (``answer_log``, the authoritative signature versus
    #: the in-memory seed baseline, ``record_id``); nothing is estimated.
    at_risk: dict


def _reset_response(
    data: dict,
    *,
    mode: str,
    status: str,
    http: int,
    refusal_reason: str | None = None,
) -> JSONResponse:
    # ``refused``/``refusal`` are the workspace layer's internal verdict; the HTTP
    # contract expresses the same thing as ``status`` + ``refusal_reason``.
    payload = {k: v for k, v in data.items() if k not in ("refused", "refusal")}
    resp = DemoResetResponse(
        status=status, mode=mode, refusal_reason=refusal_reason, **payload
    )
    return JSONResponse(status_code=http, content=resp.model_dump())


@router.post(
    "/demo/reset",
    tags=[TAG_DEMO],
    summary="Reset the Example Workspace",
    # TWO CORRECTIONS, and both are about scope rather than style.
    #
    # 1. The header REQUIREMENT was stated only in the `409` sub-description, so the
    #    main description read as though this operation could be called bare. The
    #    handler docstring has always required a scope; the contract now says so
    #    first.
    # 2. Every "the workspace" here named a scope this operation CANNOT touch.
    #    `demo_reset` refuses before any other gate when `scope is None`, and
    #    `reset_to_canonical_seed(session_id=scope)` addresses `scope_root(scope)`
    #    only. Left as "the workspace", the sentence "Restores the workspace to
    #    exactly the five canonical built-in example records" describes a destructive
    #    act on the ordinary workspace that this endpoint has no path to perform.
    description=(
        "REQUIRES the `X-Isaac-Tutorial-Session` header, and refuses with `409` "
        "(`tutorial_scope_required`) without one, mutating nothing. Everything it "
        "classifies, reports and restores is the worked-example session that header "
        "names; it addresses no other scope and cannot remove, restore or modify a "
        "record in the ordinary workspace.\n\n"
        "Restores that session to exactly the five canonical built-in example "
        "records and reports the before/after counts, the removable set, a state "
        "histogram, and a derived summary of the confirmed work the reset would "
        "discard. `mode: \"preview\"` classifies only and mutates nothing; "
        "`mode: \"execute\"` additionally requires the exact confirmation phrase "
        "and the `plan_digest` the preview returned. It accepts no caller-supplied "
        "ids or paths — any extra field is rejected — it removes only records it "
        "can classify as records this application itself created, and it refuses to "
        "remove anything at all if any record is ambiguous. No filesystem path "
        "appears in the response.\n\n"
        "**The `plan_digest` precondition.** `preview` returns an opaque digest of "
        "the session it classified. `execute` must send it back, and the reset "
        "runs only if that session still matches it. Without this, a client that "
        "previewed, showed a confirmation dialog, and executed a while later would "
        "destroy anything committed in between — the operator would have approved a "
        "classification that no longer held. A missing digest is `428` and mutates "
        "nothing; a stale one is `412`. Every response carries the CURRENT digest, so "
        "a `412` can be recovered from in one further request.\n\n"
        "The digest is also re-checked PER RECORD, inside that record's own lock and "
        "immediately before it is touched, because a per-record write can otherwise "
        "land between the first check and the mutation. A write in that window is "
        "therefore never destroyed: the reset refuses instead. That is the one "
        "refusal that can leave earlier records already reset, and the response's "
        "measured counts say so — see the `412` description.\n\n"
        "There is deliberately no general per-experiment delete operation."
    ),
    response_description=(
        "The reset outcome: `ok` when it proceeded, or `refused` with a typed "
        "`refusal_reason` and the same counts when it declined."
    ),
    responses={
        **_R_UNAUTHORIZED,
        **_R_TUTORIAL_SCOPE,
        403: {
            "description": (
                "Refused because the deployment is not in synthetic-only data "
                "mode. Nothing was removed; the reported counts come from a "
                "read-only classification."
            )
        },
        409: {
            "description": (
                "Refused without mutating, for one of three reasons, distinguished by "
                "the typed reason in the body: no `X-Isaac-Tutorial-Session` header "
                "was sent, so there is no worked-example session to reset "
                "(`tutorial_scope_required`); the `execute` confirmation phrase was "
                "missing or wrong (`confirmation_required`); or at least one record "
                "could not be classified as a record this session itself created "
                "(`ambiguous_records_present`)."
            )
        },
        412: {
            "description": (
                "Refused: the `plan_digest` does not match, so the workspace changed "
                "after the preview the operator approved. The response carries the "
                "current `plan_digest`; preview again and let the operator re-approve "
                "what they would now lose.\n\n"
                "Almost always nothing was mutated. The one exception is deliberate "
                "and is disclosed by the counts rather than hidden: the precondition "
                "is re-checked per record, inside that record's own lock, immediately "
                "before it is touched — so a write that lands mid-reset is never "
                "destroyed, and the reset stops there instead. Records reset before "
                "that point stay reset. `removed_count` and `final_count` are "
                "MEASURED, so they describe what is actually on disk either way, and "
                "the status is never `ok`."
            )
        },
        428: {
            "description": (
                "Refused without mutating: `plan_digest` was omitted. Every execute "
                "requires the digest from its own preview, so a reset can never run "
                "against a session nobody looked at."
            )
        },
    },
)
def demo_reset(
    scope: TutorialScopeDep,
    req: DemoResetRequest = Body(
        description=(
            "`mode` is `preview` or `execute`. `execute` also requires "
            "`confirmation` to be the exact phrase the UI displays and "
            "`plan_digest` to be the digest its own preview returned. Any other "
            "field is rejected."
        ),
    ),
):
    """Reset ONE worked-example session to the canonical five.

    REQUIRES tutorial scope. Called without ``X-Isaac-Tutorial-Session`` it refuses
    with ``409 {"error": "tutorial_scope_required"}`` and mutates nothing. The
    refusal is checked before every other gate, including the synthetic-only gate,
    because without a scope there is no workspace to classify and any counts reported
    alongside a refusal would be counts about the wrong thing.

    Every safety property of the underlying reset is preserved, merely scoped: the
    preview -> execute ``plan_digest`` precondition (428 absent / 412 stale) verified
    inside the same critical section as the mutation, ``record_lock`` held over
    managed-legacy removal as well as canonical re-materialisation, ``final_count``
    measured rather than asserted, the ``is_synthetic_only()`` gate, and the
    provenance rule that a record lacking the managed-source marker classifies
    AMBIGUOUS and forces a refusal with zero mutation.
    """
    # demo_reset is a single-user, confirmation-gated admin reset spanning MULTIPLE
    # ids: an rmtree of the managed-legacy records plus a re-materialisation of the
    # five canonical ones. It IS coordinated with the per-record mutation locks —
    # ``reset_to_canonical_seed`` takes ``record_lock(id, session_id=...)`` around
    # every id it touches, one at a time — and its cross-record precondition is the
    # ``plan_digest`` checked below rather than a single ETag.
    if scope is None:
        return _tutorial_scope_required("POST /api/demo/reset")
    mode = req.mode

    # Governance gate: refuse outside synthetic-only mode, before any precondition is
    # even considered (classification is read-only, so it is safe to report counts
    # alongside the refusal).
    if not ws.is_synthetic_only():
        data = ws.reset_to_canonical_seed(dry_run=True, session_id=scope)
        return _reset_response(
            data,
            mode=mode,
            status="refused",
            http=403,
            refusal_reason="not_synthetic_only",
        )

    # Preview NEVER mutates: classify only. It has no precondition to satisfy — it is
    # what PRODUCES the precondition for the execute that may follow.
    if mode == "preview":
        data = ws.reset_to_canonical_seed(dry_run=True, session_id=scope)
        return _reset_response(
            data,
            mode=mode,
            status="refused" if data["refused"] else "ok",
            http=200,
            refusal_reason=data["refusal"],
        )

    # Execute, gate 1 — the exact confirmation phrase. Checked BEFORE the digest so a
    # mistyped phrase keeps its long-standing 409 and stays distinguishable from a
    # precondition problem the operator cannot fix by typing.
    if req.confirmation != _RESET_CONFIRMATION:
        data = ws.reset_to_canonical_seed(dry_run=True, session_id=scope)
        return _reset_response(
            data,
            mode=mode,
            status="refused",
            http=409,
            refusal_reason="confirmation_required",
        )

    # Execute, gate 2 — the precondition must be PRESENT. Fail-closed: an omitted
    # digest is never treated as "no opinion", because that is exactly the blind
    # overwrite this slice exists to remove.
    digest = (req.plan_digest or "").strip()
    if not digest:
        data = ws.reset_to_canonical_seed(dry_run=True, session_id=scope)
        return _reset_response(
            data,
            mode=mode,
            status="refused",
            http=428,
            refusal_reason="plan_digest_required",
        )

    # Execute, gate 3 — the precondition must MATCH, and the match is verified inside
    # the same critical section as the mutation (so it is not re-checked here).
    data = ws.reset_to_canonical_seed(
        dry_run=False, expected_plan_digest=digest, session_id=scope
    )
    if data["refusal"] == "plan_digest_stale":
        return _reset_response(
            data, mode=mode, status="refused", http=412, refusal_reason="plan_digest_stale"
        )
    if data["refused"]:
        return _reset_response(
            data,
            mode=mode,
            status="refused",
            http=409,
            refusal_reason="ambiguous_records_present",
        )
    return _reset_response(data, mode=mode, status="ok", http=200)


# --- 3. list ------------------------------------------------------------------


def _hydration_disclosure(outcome: ws.HydrationOutcome) -> dict | None:
    """The `incomplete` block for a list response, or ``None`` when it is whole.

    ``None`` RATHER THAN ``{"complete": true}``, and the choice is deliberate. An
    absent key is the honest shape for "this response makes no completeness
    claim": the presence of the block is the machine-readable signal, so a client
    branches on one thing rather than on a flag it has to read correctly, and a
    healthy list is byte-identical to the one this operation has always returned.

    NO COUNT IS INVENTED. ``missing_count`` is ``None`` and says so explicitly
    rather than being omitted — "unknown" is the answer, and an absent field would
    leave a reader to decide whether it means zero. A pass that stopped part-way
    genuinely does not know how many rows it never reached, and ``CLAUDE.md`` §5
    forbids supplying a number for it.

    IT CANNOT RAISE. The message comes from
    ``HydrationOutcome.message()``, which falls back rather than indexing — this
    is the LIST path, and a disclosure that could 500 while disclosing a
    degradation would be worse than the degradation.
    """
    if outcome.complete:
        return None
    return {
        "reason": outcome.reason,
        "missing_count": None,
        "message": outcome.message(),
    }


@router.get(
    "/experiments",
    tags=[TAG_EXPERIMENTS],
    summary="List Workspace Experiments",
    description=(
        "One summary row per experiment currently in the workspace: its id, "
        "title, derived status, creation time, how many blocking questions are "
        "still open, how many fields carry evidence, whether it has been "
        "exported, and the exported record id when there is one. Rows for the "
        "five built-in example records also carry a derived, never-stored "
        "`scenario` label naming which example the row is; it is null for "
        "any other record. Read-only, and it states no validity verdict.\n\n"
        "**This list is not a completeness claim, and on one deployment shape it "
        "cannot be — so it tells you when it is short.** Where experiments are "
        "stored in a database, a row whose working copy is missing — a pod restart "
        "discards it — is restored on read before the list is built. If that "
        "restore does not finish, this operation degrades to the working copies it "
        "can see rather than failing, so the list may be SHORT. It never asserts "
        "that the rows it did not return do not exist, and it no longer leaves that "
        "to be inferred: the response then carries an `incomplete` object, and a "
        "read of one such record by id answers `503` rather than a `404` that would "
        "claim it is gone.\n\n"
        "**`incomplete` is ABSENT when the list is whole**, so its presence is the "
        "signal — a client does not have to interpret a flag. When present it "
        "carries a `reason` of `store_unavailable` (the database did not answer; "
        "`GET /api/health` reports `experiment_storage.state: \"unavailable\"` in "
        "that state too) or `restore_failed` (everything else that can stop the "
        "restore: a working copy that could not be written, with a full "
        "`emptyDir` the realistic trigger; a stored row the server refused as "
        "unplaceable; or a store it could not resolve at all). The second is why "
        "this disclosure exists in band at all: the database is typically healthy "
        "there, so `/api/health` correctly goes on reporting `durable`, and "
        "nothing outside this response can tell you the list is short. "
        "`missing_count` is always `null` — a restore that did not finish does "
        "not know how many rows it did not reach, and a number would be invented. "
        "`message` is a fixed sentence naming no host, path or credential, and it "
        "does NOT promise that retrying clears a `restore_failed`.\n\n"
        "**Treat a short list as evidence about this read, never as an "
        "inventory.**"
    ),
    response_description=(
        "One summary row per experiment this read could enumerate, and — only when "
        "the list may be short — an `incomplete` object saying so. **Rows are "
        "never silently dropped:** if hydration could not complete, the response "
        "says it could not."
    ),
    responses={**_R_UNAUTHORIZED, **_R_TUTORIAL_SCOPE},
)
def list_experiments(scope: TutorialScopeDep) -> dict:
    experiments, hydration = ws.list_experiments_with_hydration(scope)
    body: dict = {"experiments": [_summary(e) for e in experiments]}
    disclosure = _hydration_disclosure(hydration)
    if disclosure is not None:
        body["incomplete"] = disclosure
    return body


# --- 3b. create ---------------------------------------------------------------
#
# THE FIRST RECORD-CREATION SURFACE THIS APPLICATION HAS EVER HAD, and it is
# deliberately the smallest one that can exist: a name, an optional note, and
# nothing scientific at all.
#
# WHAT THE ABSENCE OF THIS ROUTE USED TO BE DOING. Three product strings claim
# that nothing in this build adds a BUILT-IN EXAMPLE record to the ordinary
# workspace (the mode chip's accessible name, the `tutorial` tag description
# above, and the Statistics lead sentence). Until now their stated justification
# was "this build exposes no record-creation surface at all", pinned by
# `test_tutorial_scope.py::test_create_experiment_has_no_caller_in_the_api_package`.
#
# ALL THREE STRINGS ARE STILL TRUE, and their justification has moved rather than
# weakened. They are about built-in EXAMPLE records, and this route cannot produce
# one:
#
#   * the id is minted server-side by `create_experiment`'s `rid = id or
#     new_record_id()` with no `id=` argument anywhere on the path, so the five
#     fixed canonical ids are unreachable;
#   * `CreateExperimentRequest` sets `extra="forbid"`, so a client cannot even
#     name an `id` field — the request is rejected, not ignored;
#   * `_materialise_seed`, `reset_to_canonical_seed` and `ensure_tutorial_seeded`
#     each RAISE `InvalidTutorialSession` on a `None` session id, so no seeding
#     path can put an example in the ordinary scope;
#   * and `PostgresOrdinaryStore.refuse_if_not_persistable` raises on a canonical
#     id whatever the scope, so one cannot be made durable either.
#
# WHY IT REFUSES INSIDE A WORKED-EXAMPLE SESSION rather than quietly creating in
# the ordinary scope. Either alternative is worse. Creating into the SESSION would
# put a user's own record inside a workspace that is discarded on a timer — the
# examples are temporary by design and a real record must never inherit that.
# Creating into the ORDINARY scope while the caller is reading the session would
# write a record the caller cannot see, into a list they are not looking at. The
# refusal is explicit, typed, and mirrors `/api/demo/run`'s opposite requirement.


class CreateExperimentRequest(BaseModel):
    """A new experiment: a title, and optionally a short note about it.

    ``extra="forbid"`` is the load-bearing line. It is what makes "no
    client-supplied record id" a property of the CONTRACT rather than of this
    handler remembering not to read one: `{"id": "..."}` is a 422, and so is any
    other field a future client invents.

    There is deliberately no scientific field here. Everything an ISAAC record
    needs — technique, facility, sample, energy window, series, descriptors — is
    evidence-bearing, and this form has no evidence to attach. Those are asked
    for by the Guided Completion workflow, where an answer is recorded with its
    confirmation, rather than typed into a create form where it would arrive as
    an unsourced assertion.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        max_length=200,
        description="What to call this experiment. Required, and it is not a scientific claim.",
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description=(
            "Optional free-text note about what this experiment is. Stored as the "
            "record's source description; it is never parsed and never becomes a "
            "scientific value."
        ),
    )


@router.post(
    "/experiments",
    status_code=201,
    tags=[TAG_EXPERIMENTS],
    summary="Create an Experiment",
    description=(
        "Creates a new, empty experiment in the ordinary workspace and returns its "
        "full detail bundle, so a client can go straight to it.\n\n"
        "It takes a title and an optional note, and nothing else. No scientific "
        "value is invented: the new record starts with every scientific field "
        "genuinely empty and with the blocking questions an ISAAC record has to "
        "answer already open, which is what the guided completion workflow then "
        "works through. The record id is always minted by the server — a "
        "caller-supplied id is rejected, as is any other unrecognised field.\n\n"
        "It refuses with `409` when the `X-Isaac-Tutorial-Session` header is "
        "present, and writes nothing. A worked-example session is temporary and is "
        "discarded on a timer; a record you created must not inherit that, and it "
        "must not be written into a workspace you are not currently looking at "
        "either.\n\n"
        "Whether the new experiment is stored durably depends on this deployment. "
        "`GET /api/health` reports which, in `experiment_storage`, and the reader "
        "is told the same thing before they create anything.\n\n"
        "Where this deployment stores experiments in a database and that database "
        "does not accept the write, the request fails with `503` and nothing is "
        "created. It is never quietly written somewhere temporary instead: you "
        "have been told your work is kept, and a create that could not keep it "
        "says so rather than looking like it succeeded."
    ),
    response_description="The created experiment's detail bundle, with its `ETag`.",
    responses={
        **_R_UNAUTHORIZED,
        **_R_TUTORIAL_SCOPE,
        409: {
            "description": (
                "The request carried a worked-example session header. This "
                "operation acts only on the ordinary workspace. Nothing was "
                "created."
            )
        },
        412: {
            "description": (
                "This deployment stores experiments in its own database, and that "
                "database already holds a different record under the id this "
                "request would have used. Nothing was created. The body is the "
                "same `stale_write` shape the record write operations return, "
                "with `expected_rev` and `expected_version` null because a create "
                "carries no `If-Match`. Reaching this requires an id collision, "
                "which this application does not produce — it is documented "
                "because the response is declared, not because it is expected."
            )
        },
        503: {
            "description": (
                "This deployment stores experiments in its own database, and that "
                "database did not accept the write. Nothing was created, and "
                "nothing was written to the server's workspace directory either. "
                "The response names no host, path or credential."
            )
        },
    },
)
def create_experiment_route(
    scope: TutorialScopeDep, body: CreateExperimentRequest, response: Response
):
    if scope is not None:
        return JSONResponse(
            status_code=409,
            content={
                "error": "ordinary_scope_required",
                "operation": "POST /api/experiments",
                "header": TUTORIAL_SESSION_HEADER,
                "message": (
                    "Experiments are created in the ordinary workspace, never "
                    "inside a worked-example session — a session is discarded when "
                    "it expires. Leave the worked example, then create it. Nothing "
                    "was created."
                ),
            },
        )
    title = body.title.strip()
    if not title:
        # `min_length=1` accepts a string of spaces; a name that is only
        # whitespace names nothing, so it is refused with the same typed shape a
        # schema rejection would have produced.
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_title",
                "message": "An experiment needs a title. Nothing was created.",
            },
        )
    description = (body.description or "").strip() or None
    # The ONE call. Which backend stores it is `experiment_repository`'s decision
    # and this route deliberately cannot tell — that is what keeps a future
    # durable repository from needing a route change.
    exp = experiment_repository.repository().create(title=title, description=description)
    detail = _detail(exp)
    detail.update(vc.version_fields(exp))
    response.headers["ETag"] = exp.etag()
    return detail


# --- 4. detail ----------------------------------------------------------------


@router.get(
    "/experiments/{experiment_id}",
    tags=[TAG_EXPERIMENTS],
    summary="Get One Experiment's Detail Bundle",
    description=(
        "The full detail bundle for one experiment: its summary row plus whether "
        "the draft passes the no-guessing checks, the exported artifact filenames "
        "(basenames only, never a server path), the source files it was extracted "
        "from, the derived workflow progression, the exported-artifact freshness "
        "state, and the current revision metadata.\n\n"
        "The response carries the record's current `ETag`. Send it back as "
        "`If-None-Match` to receive `304` while the record is unchanged. "
        "Read-only."
    ),
    response_description="The experiment detail bundle, with the current `ETag`.",
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        304: {
            "description": (
                "The record is unchanged since the `If-None-Match` validator "
                "supplied. No body; the current `ETag` is returned."
            )
        },
    },
)
def get_experiment(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    if_none_match: str | None = Header(
        default=None,
        alias="If-None-Match",
        description=(
            "Optional. A previously received `ETag`; while it still matches, the "
            "response is `304` with no body."
        ),
    ),
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    # Conditional GET (P27.6 live-sync polling): if the client's If-None-Match
    # matches the current strong validator, the record is unchanged -> 304 with the
    # ETag and NO body (a cheap change signal; polling is only a signal, the fetched
    # snapshot remains authoritative).
    if _if_none_match_hit(if_none_match, exp):
        return Response(status_code=304, headers={"ETag": exp.etag()})
    detail = _detail(exp)
    detail.update(vc.version_fields(exp))
    response.headers["ETag"] = exp.etag()
    return detail


# --- 5. draft (grouped) -------------------------------------------------------


@router.get(
    "/experiments/{experiment_id}/draft",
    tags=[TAG_DRAFTS],
    summary="Get a Record's Draft Fields",
    description=(
        "This record's draft fields, grouped into the stable sections the record "
        "review screen renders. Each field carries its label, official path, "
        "current value, the status derived from its evidence, and the kinds of "
        "source that evidence came from. Read-only; the response carries the "
        "record's current `ETag`."
    ),
    response_description="The draft's fields, grouped, with the current `ETag`.",
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def get_draft(scope: TutorialScopeDep, experiment_id: ExperimentId, response: Response):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    response.headers["ETag"] = exp.etag()
    return serialize.draft_to_groups(exp.draft)


# --- 6. pending ---------------------------------------------------------------


def _example_scope(experiment_id: str) -> bool:
    """Whether this record may be shown the committed walkthrough example answers.

    True for the five canonical seed ids and nothing else. This is the check that
    makes the endpoint description's "for the built-in examples only" a fact rather
    than an aspiration — see the long note in ``serialize._demo_answer_for`` for
    what it used to be. Reading ``ws.CANONICAL_IDS`` directly keeps ONE definition
    of "canonical", the same one reset and removal already enforce.
    """
    return experiment_id in ws.CANONICAL_IDS


def _mutation_pending_response(exp, experiment_id: str, *, unit_run_id: str | None) -> dict:
    """The recomputed question list a MUTATION returns — BOUNDED, and saying so.

    THE MEASURED DEFECT, and it is the write path rather than the read path, which is
    why it is the worse half. All four mutations (`POST /answers`, `POST /edit`, and
    the two run-level equivalents) returned `serialize.pending_to_list(entries=
    exp.pending())` — EVERY open question of the WHOLE record, unbounded. Measured
    in-process over HTTP on `c153ec9`, answering ONE question on ONE run::

           runs   POST /runs/{run_id}/answers -> 200      entries
             25                        44,840 B               74
            250                       443,542 B              749
           1000                     1,773,294 B            2,999

    So a scientist working through a 1000-run record downloaded 1.77 MB per
    submission, on every submission, to learn whether the one question they had just
    answered was still open.

    WHY THE DEFAULT IS BOUNDED HERE AND UNBOUNDED ON `GET /pending`. They are
    different acts. A GET is a client ASKING what is unresolved, and answering it with
    a page a caller did not request is exactly the silent truncation this repository
    refuses. A mutation response is a report the server volunteers alongside a write;
    nobody asked for it to be the whole record, and it is a contract change made
    deliberately and documented in the operation descriptions.

    NOTHING IS SILENTLY TRUNCATED AND NOTHING BECOMES UNDISCOVERABLE. `pending_page`
    is ALWAYS present — including when the window IS the whole set (`complete: true`),
    so a client never has to infer from absence — and it reports how many entries were
    withheld. `GET /pending` still answers completely by default, so every open
    question remains reachable in one request.

    THE WINDOW IS ANCHORED ON THE UNIT THAT WAS WRITTEN. See
    `serialize.pending_mutation_window`: a plain head-of-list window would not contain
    run 900's questions, and `GuidedCompletion` decides "was my answer applied?" by
    asking whether its question is still in this list — so an answer the core REFUSED
    would have read as applied. `unit_run_id` is the run this write addressed, or
    `None` for a record-level write.

    `pending_count`, `status`, `export_ready` and `workflow` are untouched by this:
    they are derived from `Experiment.pending()` in full, before any bounding, so the
    counts on the response continue to agree with the record rather than with the page.
    """
    entries = exp.pending()
    window, page = serialize.pending_mutation_window(entries, unit_run_id=unit_run_id)
    result = serialize.pending_to_list(
        exp.draft,
        ws.load_demo_answers(),
        example_scope=_example_scope(experiment_id),
        entries=window,
    )
    result["pending_page"] = page
    return result


#: THE ONE PARAGRAPH THE FOUR MUTATION OPERATIONS SHARE, written once.
#:
#: All four return the same recomputed-question bundle and all four are bounded by the
#: same policy, so four hand-written copies would be four places for the sentence to
#: drift — and `apps/web/src/test/apiFixtures.ts` holds a transcribed copy of every
#: one of them, which `test_contract_description_parity.py` compares byte-for-byte.
#: The window size is INTERPOLATED from `serialize.PENDING_WINDOW` for the same reason
#: `_RUN_LIMIT_DESC` interpolates `RUN_PAGE_MAX`: a retyped bound is a copy free to
#: drift silently, and the copy that drifts is the one published in the contract.
_BOUNDED_PENDING_PARAGRAPH = (
    "THE REFRESHED QUESTION LIST IS BOUNDED. A record's open questions grow with its "
    "runs, and at 1,000 runs this response measured 1.77 MB — the whole record's "
    "question set, returned on every submission, to report one answer. It now carries "
    f"at most the first {serialize.PENDING_WINDOW}, plus every still-open question of "
    "the unit this write addressed, so the question you just answered is always in it. "
    "`pending_page` is ALWAYS present and reports `total`, `returned`, `withheld` and "
    "whether the list is `complete`, so a page can never be mistaken for the whole "
    "set, and `GET /api/experiments/{experiment_id}/pending` still answers completely "
    "by default, so no question becomes unreachable. `status`, `workflow` and the "
    "record's pending count are derived from the whole list BEFORE any bounding and "
    "are unchanged."
)

#: The largest page ONE bounded `GET /pending` request may ask for.
#:
#: Same shape of decision as ``RUN_PAGE_MAX`` above, and the same non-limit: OMITTING
#: `limit` STILL RETURNS EVERY OPEN QUESTION. This bounds a single bounded response,
#: never how many questions a record may have, and `total` always reports how many
#: there are.
#:
#: 500 is set against the measured per-entry cost rather than guessed: an entry
#: serialises to ~591 bytes (`serialize`'s note above `PENDING_WINDOW` records the
#: measurement and the harness), so a full page is ~295 KB — the worst case a client
#: may ask for in one request, which is not the page a UI should request. The window a
#: MUTATION returns is `serialize.PENDING_WINDOW` (50) and is deliberately a different,
#: much smaller number: that one is a policy applied to a caller who did not ask.
#:
#: ~~an entry serialises to ~627 bytes … so a full page is ~313 KB~~ — **both figures
#: were overstated and are corrected in place.** An independent review re-measured the
#: page and got 295,295 B; so did this correction, exactly. Neither number was doing
#: any work beyond justifying the 500, which is unchanged — but a justification a
#: reader cannot reproduce is worse than none, so here is the one command that produces
#: it, against the same no-explicit-label harness `serialize`'s table used:
#:
#:     # after building a 1,000-run record (see serialize.py's note)
#:     len(c.get(f"/api/experiments/{eid}/pending?limit=500").content)  -> 295295
PENDING_PAGE_MAX: int = 500

#: THE BOUND IS INTERPOLATED, NOT RETYPED — same reason as ``_RUN_LIMIT_DESC``.
_PENDING_LIMIT_DESC = (
    f"Maximum questions to return, 1–{PENDING_PAGE_MAX}. OMIT to return every open "
    "question: this parameter bounds one response and is never a limit on how many "
    "questions a record may have. When you send it, the response carries a "
    "`pending_page` block reporting the total and how many were withheld."
)

_PENDING_OFFSET_DESC = (
    "How many questions to skip, in the order this operation returns them (the "
    "record's own, then each run's in run order). An offset past the end is CLAMPED "
    "to an empty page rather than refused, and `pending_page.total` tells the client "
    "it ran off the end."
)

_PENDING_RUN_ID_DESC = (
    "Return only the questions owned by this run — the common case of a scientist "
    "working one measurement. Refused with `404 run_not_found` when the record holds "
    "no such run, rather than answered with an empty list that reads as 'this run has "
    "nothing left'. AN EMPTY VALUE IS A RUN ID THE RECORD DOES NOT HOLD AND IS REFUSED "
    "THE SAME WAY — over HTTP that is `?run_id=`, and to an MCP tool it is `run_id: "
    "\"\"` — naming `\"\"` as the id that was not found; it is "
    "not treated as if the parameter were absent, because a caller that interpolated "
    "nothing into a run filter would otherwise be handed the WHOLE record and read it "
    "as that run's questions. `pending_page.record_total` still reports the WHOLE "
    "record's open question count, so a filtered read can never be mistaken for the "
    "record's state."
)


@router.get(
    "/experiments/{experiment_id}/pending",
    tags=[TAG_DRAFTS],
    summary="List a Record's Open Blocking Questions",
    description=(
        "The questions that are still blocking this draft, each with the stable "
        "key an answer must be submitted under, what the question is about, and — "
        "for the built-in examples only — a clearly labelled suggested "
        "answer that is never applied automatically. Read-only; the response "
        "carries the record's current `ETag`.\n\n"
        "WITHOUT PARAMETERS THE ANSWER IS COMPLETE: every open question on the "
        "record, its runs' included. A record's question count grows with its runs, "
        "so `run_id`, `offset` and `limit` let a client bound what it asks for — but "
        "bounding is something a client asks for, never something imposed on one that "
        "does not know to page. A `run_id`, a NON-ZERO `offset`, or a `limit` bounds "
        "the read, and the response then gains a `pending_page` block reporting "
        "`total`, `returned`, `withheld`, `record_total` and whether the list is "
        "`complete`, so a page can never be mistaken for the whole set.\n\n"
        "**`offset=0` ON ITS OWN BOUNDS NOTHING** — it is this route's default, so a "
        "request sending only it is the unbounded read and carries no `pending_page`. "
        "An earlier revision said \"send any of the three\", which was false for "
        "exactly that case, and a client told to page will plausibly open with it. "
        "And `complete` is RELATIVE TO THE FILTER: under a `run_id` it says that run "
        "has nothing further, never that the record has — `record_total` is the "
        "record's own count and is why it travels beside `total`."
    ),
    response_description="The open blocking questions, with the current `ETag`.",
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        **_R_RUN_NOT_FOUND,
    },
)
def get_pending(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    run_id: Annotated[str | None, Query(description=_PENDING_RUN_ID_DESC)] = None,
    offset: Annotated[int, Query(ge=0, description=_PENDING_OFFSET_DESC)] = 0,
    limit: Annotated[
        int | None, Query(ge=1, le=PENDING_PAGE_MAX, description=_PENDING_LIMIT_DESC)
    ] = None,
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    # AN UNKNOWN RUN IS REFUSED, NOT ANSWERED WITH AN EMPTY PAGE. A filter that
    # silently matches nothing is a surface answering less than it claims: a client
    # that mistyped a run id would read `total: 0` as "this run has no open
    # questions". `_run_not_found` is the same body every other run route uses.
    if run_id is not None and exp.get_run(run_id) is None:
        return _run_not_found(experiment_id, run_id)
    # SEE `list_runs`' ETag NOTE. This tag is the EXPERIMENT's, so two different pages
    # of the same record carry the same tag. Harmless while nothing reads
    # `If-None-Match` here, and a trap for whoever adds a conditional GET next.
    response.headers["ETag"] = exp.etag()
    # `exp.pending()`, NOT `exp.draft` — see `serialize.pending_to_list`'s `entries`
    # override. This route was run-blind while the detail response's `pending_count`
    # was not, so the two disagreed the moment a record had a run.
    entries = exp.pending()
    bounded = run_id is not None or offset != 0 or limit is not None
    # THE UNBOUNDED RESPONSE IS BYTE-IDENTICAL TO WHAT IT ALWAYS WAS — same single
    # `pending` key, no page block. `pending_page` is not "always present, sometimes
    # trivial" here, because the whole point of the default is that a consumer which
    # never learned to page is handed nothing new to interpret. The MUTATION responses
    # make the opposite choice for the opposite reason: they are bounded whether the
    # caller asked or not, so they must say so unconditionally.
    if not bounded:
        return serialize.pending_to_list(
            exp.draft,
            ws.load_demo_answers(),
            example_scope=_example_scope(experiment_id),
            entries=entries,
        )
    window, page = serialize.pending_slice(
        entries, run_id=run_id, offset=offset, limit=limit
    )
    result = serialize.pending_to_list(
        exp.draft,
        ws.load_demo_answers(),
        example_scope=_example_scope(experiment_id),
        entries=window,
    )
    result["pending_page"] = page
    return result


# --- 7. answers ---------------------------------------------------------------


def _value_fits_the_store(value) -> bool:
    """Bounded size, bounded depth, renderable — the half of storability that has
    nothing to do with WHICH field is being written.

    ONE DEFINITION, TWO CALLERS, AND THAT IS THE WHOLE POINT OF IT EXISTING. It is the
    first line of :func:`_correction_is_storable` (the ``/edit`` screen) and the whole of
    :func:`_refuse_unstorable_answer` (the ``/answers`` screen). Extracting it is
    deliberate rather than tidy: this module's own history says a guard "existing two
    thousand lines away is not a defence", and a second copy of `8 MiB` is how the two
    ingresses end up disagreeing about how big a spectrum may be.

    IT IS DELIBERATELY NOT THE SHAPE PREDICATES. ``/edit`` also asks
    ``is_series_shaped``/``is_descriptor_shaped``/``is_qc_shaped``/``is_sha256_shaped``,
    and ``/answers`` MUST NOT: on the answering path a wrong-TYPED value leaves the
    blocker OPEN, so the response already tells the caller the question was not answered,
    and that behaviour is pinned by ``test_answers_wrong_type.py`` and by a browser spec.
    Size, depth and renderability have no such fallback — an 8 MiB ``qc.evidence`` is
    perfectly well-shaped, so nothing downstream declines it and it goes to disk.

    THE BOUND IS ``_MAX_CORRECTION_BYTES`` (8 MiB) ON BOTH PATHS, not the run path's
    64 KiB. A reduced spectrum is legitimately large, and the two ingresses accept the
    same values, so the same number is the only defensible one: a smaller bound here
    would refuse on ``/answers`` what ``/edit`` accepts for the same field.
    """
    return _is_storable_value(value, max_bytes=_MAX_CORRECTION_BYTES)


def _correction_is_storable(key: str, value) -> bool:
    """Can ``apply_corrections`` store this value, AND can the app survive doing so?

    TWO PREVIOUS VERSIONS OF THIS WERE WRONG IN THE SAME WAY — they answered a narrower
    question than the name, and a reviewer measured what got through each time:

    * it IMPORTS the shape predicates now instead of re-implementing them. The last version
      copied ``is_series_shaped``'s body under a docstring claiming it "mirrors the guards
      … rather than restating them loosely". Copying is restating, and it created exactly
      the second definition that comment warned about.
    * it applies :func:`_is_storable_value` as well, which is where depth, renderability
      and size live. Without it, ``NaN`` and ``Infinity`` were accepted and written as bare
      JSON literals — making ``experiment.json`` invalid JSON and every later export raise
      ``ValueError: Out of range float values are not JSON compliant`` forever — and a lone
      surrogate crashed the response render after the write had committed. The run write
      path already guards all three; this route did not, and the guard existing two
      thousand lines away is not a defence.
    * it is asked of EVERY key in the shaped body, not just ``series`` and ``descriptor``.
      Asset-URI keys with a non-string value, and ``descriptor_label`` / ``edge`` at any
      type, were silently absorbed with a 200 — the outcome this block's own comment calls
      forbidden.

    The size bound is deliberately NOT the run path's 64 KiB: a reduced spectrum is
    legitimately large. 8 MiB bounds a pathological payload without putting a scientific
    limit on real data, and it is a bound on ONE corrected value rather than on the record.
    """
    if not _value_fits_the_store(value):
        return False
    if key == "series":
        return is_series_shaped(value)
    if key == "descriptor":
        return is_descriptor_shaped(value)
    if key == "descriptor_label":
        # It is rendered as a label; only a string is one.
        return isinstance(value, str)
    if key == "edge":
        return isinstance(value, (str, int, float))
    if key == "qc":
        return is_qc_shaped(value)
    # Anything else in the shaped body is an asset sha256, keyed by URI.
    #
    # `isinstance(value, str)` WAS NOT ENOUGH, and a reviewer measured what it let
    # through: `"Z" * 64`, `"abc"`, 63 hex chars and 65 hex chars each passed this
    # guard, were then declined by `apply_corrections` as malformed, and this route
    # answered **200 having changed nothing** — the outcome the block below calls
    # forbidden, in the one key where malformation is a question of FORMAT rather
    # than of type. `is_sha256_shaped` is imported rather than restated for the same
    # reason the other two predicates are.
    return is_sha256_shaped(value)


def _edge_derivations_in(draft: dict) -> list:
    """The ``implicit[]`` entries an ``edge`` answer can be written onto.

    THE PREDICATE IS ``complete.apply_answers``'s OWN, restated as a question this
    module can ask BEFORE calling it: both the answering and the correcting writer loop
    ``draft["implicit"]`` looking for ``imp.get("about") == "edge"``, and write only into
    an entry they find. There is no branch that creates one.
    """
    return [
        entry
        for entry in (draft.get("implicit") or [])
        if isinstance(entry, dict) and entry.get("about") == "edge"
    ]


def _refuse_edge_with_nothing_to_confirm(
    draft: dict, apply_shape: dict, identifiers: dict
) -> JSONResponse | None:
    """``422`` for an ``edge`` answer this draft has no derivation to attach it to.

    THE DEFECT, measured by an independent security review on 2026-08-24 against a record
    created through ``POST /api/experiments``::

        POST /answers {"edge": "L3"}
          -> 200
             invalidation.changed   false
             invalidation.reason    "No change — the submitted value was identical;
                                     nothing was invalidated."
             draft["implicit"]      still absent

    That reason is false twice over — the value was neither identical nor ever stored —
    which is the EXACT defect this branch fixed for ``series``, ``qc``, ``descriptor`` and
    a pending asset hash, and left live for ``edge``. The cause is structural rather than
    accidental: ``complete.apply_answers`` writes ``edge`` only INTO an existing
    ``implicit[]`` entry whose ``about`` is ``"edge"``, and a created record has no
    ``implicit`` block at all — ``draft_builder`` is what emits that entry, and no route
    creates one.

    ── WHY REFUSING RATHER THAN MAKING IT LAND, argued against the two things the
    ── project says such a decision has to be argued against. ─────────────────────────
    **The no-guessing rule (CLAUDE.md §5).** ``implicit[]`` is the EXTRACTOR's block: an
    entry there asserts that a derivation was made from a source and could not be
    confirmed. A record created through Create Experiment has no source document and no
    derivation, so a route that synthesised the entry in order to have somewhere to put
    the answer would be manufacturing the derivation the block claims to record. The
    run-level tests already state the invariant from the other side — "no route creates
    one".

    **What the exported record can carry.** CLAUDE.md §5 puts the absorbing element and
    the edge on the implicit/sidecar path *"unless the official schema provides a native
    field"*, and it does not: there is no official path for an edge, so even a landed
    answer reaches the evidence sidecar and never the official record. Refusing therefore
    costs the caller nothing the schema was going to carry, while a 200 costs them a
    false statement about their own record.

    **And the alternative is a truth-core change.** Making ``apply_answers`` create the
    entry is an edit to ``src/isaac_records/complete.py``, which CLAUDE.md §13 protects
    and which would change what every caller of the core gets — the CLI and the exporter
    included — to close a defect that exists at one ingress.

    ── THIS IS NOT THE REFUSAL THAT WAS ALREADY TRIED AND WAS WORSE. ──────────────────
    ``_RUN_LEVEL_ANSWER_BLOCK``'s note records a previous version that refused ``edge`` on
    the record UNCONDITIONALLY, which made it answerable by no route at all and pointed
    the caller at an operation that would also have refused. This one is conditional on
    the one fact that decides whether a write can happen — *is there an entry to write
    into?* — so a record whose draft carries an edge derivation keeps taking the answer
    exactly as before, and it names NO alternative operation, because there is none and
    saying otherwise is how that version misled.

    WHAT IT DOES NOT CLAIM: it does not say the record is wrong, and it does not say the
    edge is unknowable. It says this draft holds no edge derivation for the answer to
    confirm, and that nothing was written — both of which are checkable by the caller in
    the response to a plain read.
    """
    if "edge" not in apply_shape or _edge_derivations_in(draft):
        return None
    return JSONResponse(
        status_code=422,
        content={
            "error": "no_derivation_to_confirm",
            **identifiers,
            "key": "edge",
            "keys": ["edge"],
            "message": (
                "This record carries no absorption-edge derivation, so there is "
                "nothing here for an `edge` answer to confirm and nothing was "
                "written. An edge is recorded as a confirmation of a value this "
                "application derived from a source document; it is not a field a "
                "record can be given from nothing. The official ISAAC record has no "
                "edge field, so no exported record is missing a value because of this."
            ),
        },
    )


#: The NAMED answer keys — every key an answers/edit body may carry that is not an
#: asset URI. It is a CONSTANT and :func:`_answers_to_apply_shape` branches on it,
#: rather than the two spelling the set separately, because the refusal below has to
#: know exactly what that function will and will not forward. A key added to one and
#: not the other is how a request gets refused as unrecognised while the mapper
#: happily carries it, or carried while the refusal calls it unknown.
_NAMED_ANSWER_KEYS: tuple[str, ...] = ("qc", "series", "descriptor", "descriptor_label", "edge")

#: The subset of :data:`_NAMED_ANSWER_KEYS` whose VALUE the truth core screens with an
#: exported shape predicate — ``is_series_shaped``, ``is_qc_shaped``,
#: ``is_descriptor_shaped`` — and therefore the subset on which "the core declined it
#: and left the question open" is a reachable outcome.
#:
#: ``descriptor_label`` AND ``edge`` ARE DELIBERATELY ABSENT, and the omission is a
#: decision rather than an oversight. Neither has a shape guard in
#: ``complete.apply_answers``: a non-string label and a non-scalar edge are STORED, not
#: declined, so refusing them here would not be closing a false ``200`` — it would be
#: a new refusal of a value that currently lands. That is a separate change with its
#: own argument to make, and ``/edit`` already refuses both through
#: :func:`_correction_is_storable`, so the two paths' disagreement about them is
#: pre-existing and is named here rather than quietly widened.
_SHAPE_SCREENED_ANSWER_KEYS: tuple[str, ...] = ("series", "qc", "descriptor")

#: The named answer keys that can cause a write BY THEMSELVES. ``descriptor_label`` is
#: the one that cannot: both core writers build the whole descriptor block and gate it on
#: ``descriptor is not None``, so a bare label is inert at any value. Used by
#: :func:`_resubmission_was_identical` to decide whether anything was submitted that
#: could have been compared. It is the same distinction ``_has_correction_target``
#: already makes on the correction path, where a bare label earns ``unrecognized_field``.
_WRITING_ANSWER_KEYS: frozenset[str] = frozenset({"series", "descriptor", "qc", "edge"})


def _answer_asset_uris(draft: dict, *, edit_only: bool) -> set:
    """The asset URIs an answers/edit body may key on, for ONE draft.

    ONE DEFINITION, TWO CALLERS, for the reason :func:`_value_fits_the_store` gives at
    length: :func:`_answers_to_apply_shape` decides which URI keys it FORWARDS and
    :func:`_refuse_a_body_that_names_nothing_answerable` decides which it RECOGNISES, and those two
    sets must be the same set or a URI is refused as unknown by one and accepted by the
    other. The ``edit_only`` narrowing (and the argument for it) stays documented in
    ``_answers_to_apply_shape``, which is where the measured defect was.
    """
    stored = {a.get("uri") for a in (draft.get("assets") or []) if isinstance(a, dict)}
    if edit_only:
        return stored
    pending = draft.get("pending") or []
    return {
        e.get("uri") for e in pending if isinstance(e, dict) and e.get("kind") == "asset"
    } | stored


def _dropped_answer_keys(answers_by_id: dict, draft: dict, *, edit_only: bool) -> list[str]:
    """The non-blank keys :func:`_answers_to_apply_shape` will DROP, in submission order.

    Exists so a route can KNOW that it dropped something, which it previously could not.
    That is the whole mechanism behind the false no-op reason: a key vanished before the
    truth core saw it, ``changed`` came back ``False``, and the only cause
    ``build_invalidation`` knew about was "the value was identical" — so a mistyped key
    was explained as an already-stored value.

    Blank values (``None``/``""``) are excluded because the mapper drops those at ANY
    key, recognised or not, and that has never been a mistake to report: a blank answer
    is not an answer.
    """
    known = set(_NAMED_ANSWER_KEYS) | _answer_asset_uris(draft, edit_only=edit_only)
    return [
        key
        for key, value in (answers_by_id or {}).items()
        if value not in (None, "") and key not in known
    ]


def _refuse_a_body_that_names_nothing_answerable(
    answers_by_id: dict, dropped: list[str], identifiers: dict
) -> JSONResponse | None:
    """``422 unrecognized_field`` when EVERY non-blank key would be dropped, or ``None``.

    THIS IS A CHANGE TO A PUBLISHED CONTRACT, AND IT IS DECLARED RATHER THAN SLIPPED IN.
    Both answers operations promised, in their own OpenAPI body description and in
    ``isaac_answer_questions``' tool description, that *"an UNRECOGNISED key is ignored
    rather than invented"*. That promise is narrowed: a body in which NOTHING is
    recognised is now refused by name. Every surface that stated the old rule states the
    new one (this route's body description, the run route's description,
    :data:`_R_ANSWER_REFUSED`, and the MCP tool).

    THE DEFECT THIS CLOSES, measured over HTTP at both levels and over MCP, with the
    most ordinary mistake a client can make — a mistyped key::

        POST .../answers {"sample.material.nmae": "Fe2O3"}
          -> 200
             invalidation.changed  false
             invalidation.reason   "No change — the submitted value was identical;
                                    nothing was invalidated."

    The record was never holding that key, so nothing about it can be identical.
    ``_answers_to_apply_shape`` dropped it before the truth core saw it and
    ``build_invalidation`` then explained the resulting no-op with the one cause it
    knew. This module already recorded the same sentence being measured false for a
    pending asset URI on the CORRECTION path — *"false twice over, because the value was
    neither identical nor ever stored"* — and closed that instance with exactly this
    refusal. This is the same close, on the opposite route.

    IT IS THE CORRECTION OPERATIONS' RULE, NOT A NEW ONE — which is the reason this
    boundary and not a stricter one. ``/edit`` already refuses a body that reduces to
    nothing it can act on (``not _has_correction_target`` -> ``422
    unrecognized_field``), under its own stated rule that *"an unknown field is never
    quietly swallowed"*, and already TOLERATES a ride-along key beside a recognised one.
    The answering path had neither half. Adopting both gives the two ingresses one rule,
    which is what this module keeps asking for.

    **REFUSING EVERY UNRECOGNISED KEY WAS IMPLEMENTED FIRST, MEASURED, AND REJECTED.**
    It is the stricter and at first sight more honest option — nothing silently dropped,
    ever — and it is recorded here because the measurement is the argument:

    * IT MISDIRECTS. On a fan-out record a run's asset URI is not in the RECORD's asset
      set, so a client that sent a run-owned asset hash to the record would be told its
      key is unrecognised when the useful answer is ``409 belongs_to_a_run`` naming the
      run. This module's own doctrine, from
      :func:`_refuse_correcting_an_unanswered_key`, is that *"a refusal that misdirects
      is worse than one that says nothing"*. The narrow rule cannot reach that case,
      because such a body always names something recognised too.
    * IT SPLIT THE TWO INGRESSES. ``/edit``'s ride-along tolerance is pinned by
      ``test_answers_wrong_type::test_changed_fields_names_only_what_the_apply_shape_carried``
      under an argued docstring, and its report about ride-alongs is already honest.
      Refusing on one route and tolerating on the other is the asymmetry that produced
      this defect in the first place.
    * IT BROKE 22 TESTS IN FIVE FILES WHOSE SUBJECT IS NOT THIS DEFECT — records
      seeded by harvesting one record's answers and posting them at another. Rewriting
      those helpers to pre-filter would have made them exercise LESS, not more.

    WHAT THE NARROW RULE LEAVES OPEN, STATED RATHER THAN GLOSSED. A ride-along
    unrecognised key is still dropped in silence on a ``200``. What is fixed is the
    RESPONSE'S CLAIM about it: :func:`_dropped_answer_keys` tells the route that
    something was dropped, and the route withholds the identical-value reason whenever it
    was — so the sentence that made a mistyped key look accepted can no longer be served
    over one. Naming the dropped keys in the ``200`` body would be better still and is
    NOT done here: it needs a new response field, which is the frontend's contract as
    well as this one, and it belongs to a slice that can change both.

    THE NO-GUESSING RULE IS NOT WEAKENED, WHICH IS THE OBJECTION THE OLD WORDING WAS
    PROTECTING AGAINST. *"Ignored rather than invented"* was guarding against writing a
    value for a key the application does not understand. Nothing is written in either
    case; the whole difference is in what is said about it.

    A BLANK value is still dropped at any key, recognised or not. ``{"nmae": ""}`` is not
    a mistyped answer, it is not an answer — the screen never sends one, and a body of
    blanks is still the byte-stable no-op it has always been.
    """
    if not dropped:
        return None
    non_blank = [
        key for key, value in (answers_by_id or {}).items() if value not in (None, "")
    ]
    if len(non_blank) != len(dropped):
        # Something recognised travelled. The ride-along is dropped, exactly as on the
        # correction operations, and the route withholds any claim about it.
        return None
    return JSONResponse(
        status_code=422,
        content={
            "error": "unrecognized_field",
            **identifiers,
            "key": dropped[0],
            "keys": list(dropped),
            # THE KEYS ARE ECHOED AND THE VALUES ARE NOT. `key`/`keys` are the caller's
            # own key names, which it needs in order to find the typo; echoing the VALUE
            # would put caller-supplied scientific text into an error body for no
            # purpose. `keys` names EVERY offending key rather than the first, which is
            # this module's standing convention for a refusal a client has to act on.
            "message": (
                "No open question on this record is named by these keys, and this "
                "operation will not guess which one you meant. Nothing was written. "
                "The keys it takes are the `id` values from the pending-questions "
                "operation, so read those and resend."
            ),
        },
    )


def _resubmission_was_identical(apply_shape: dict) -> bool:
    """May a ``changed=False`` outcome be reported as *"the submitted value was
    identical"*? ``False`` means the route must not claim a cause.

    THIS IS THE HALF OF THE FIX THAT IS NOT A REFUSAL, and it exists because closing
    every reachable false-``200`` still leaves one sentence that must be earned rather
    than assumed. ``dependencies.build_invalidation`` no longer names a cause unless a
    caller says it established one; this is how the four write routes establish it.

    THE ARGUMENT THAT IT IS SOUND, stated as an argument because the alternative — a
    hand-written value comparison here — is precisely what
    :func:`_refuse_answering_an_already_answered_key` refuses to do, and for the same
    reason: a route must not know where each block physically lives or how a descriptor
    compares.

    After the refusals that now run ahead of the write, a ``changed=False`` on the
    ANSWERING path is reachable in exactly two states:

    * the shape carries NO answer key at all — an empty body, or one whose every value
      was blank. Nothing was submitted, so there is nothing that could have been
      identical, and this returns ``False``.
    * the shape carries at least one answer key, every one of which the store can hold
      (``_refuse_a_body_that_names_nothing_answerable`` removed the keys it cannot act
      on and
      :func:`_refuse_unstorable_answer` removed the values it cannot keep). For an OPEN
      question ``apply_answers`` writes unconditionally once it enters the branch — the
      ``qc`` branch even APPENDS a confirmation to ``block_evidence`` — so a byte-stable
      document means the write produced the document it already had, i.e. the value was
      the stored one. For a CLOSED question ``_refuse_answering_an_already_answered_key``
      has already refused every value that DIFFERS from the confirmed one, so what
      remains is by construction identical.

    So ``changed=False`` plus a fully storable non-empty shape IS an identical
    resubmission. ``changed`` itself comes from ``save_versioned``'s comparison of the
    authoritative signature, which is a real comparison of real bytes — the claim is
    grounded there, not here.

    ONE MEASURED RESIDUE, NAMED RATHER THAN GLOSSED, because "every key was compared" is
    not what this function can actually establish. ``apply_corrections`` compares only
    the ``(status, note)`` pair of a ``qc`` block, so ``{"qc": {"status": "valid",
    "evidence": "ok", "bogus": 123}}`` against a CLOSED ``qc`` holding that status and
    note is a ``200`` reporting the value identical, while ``bogus`` was discarded
    uncompared. It is weaker than the ``descriptor_label`` case below — the two keys the
    caller is likely to care about WERE compared, and no shipped surface sends an extra
    key — and closing it would require this function to know how each block's writer
    compares, which is precisely what the paragraph above refuses to do. Closing it
    belongs to a slice that can put the comparison basis where the comparison is.

    ON THE CORRECTING PATH the same reading holds for a simpler reason: ``/edit``
    already refuses an unrecognised body, an unstorable value and an unanswered
    question, and every ``apply_corrections`` branch guards on an equality check first.

    WHY IT STILL ASKS :func:`_correction_is_storable` RATHER THAN TRUSTING THE REFUSALS.
    Two keys are deliberately outside the shape screen (see
    :data:`_SHAPE_SCREENED_ANSWER_KEYS`), and a malformed asset sha256 is deliberately
    outside it too — that one is left as a ``200`` because a shipped screen, a shipped
    UI affordance and a browser spec all depend on it being one. Each of those is a
    value the core may decline, so for each of them this must answer ``False``, and
    asking the same predicate ``/edit`` asks is how it stays right when that set moves.
    """
    named = [k for k in apply_shape if k not in ("timestamp", "asset_sha256")]
    shas = apply_shape.get("asset_sha256") or {}
    # AT LEAST ONE KEY THAT CAN CAUSE A WRITE ON ITS OWN, which `descriptor_label`
    # cannot: both core writers build the whole descriptor block and gate it on
    # `descriptor is not None`, so a bare label changes nothing at any value. Counting
    # it would have made `{"descriptor_label": "x"}` alone report "the submitted value
    # was identical" about a label the record does not store anywhere — the same false
    # sentence this function exists to stop serving, one key over.
    if not any(k in _WRITING_ANSWER_KEYS for k in named) and not shas:
        return False
    # ...AND NO KEY WHOSE VALUE NOTHING COMPARED, WHICH IS THE SAME ARGUMENT ONE KEY
    # OVER. The check above stops a BARE `descriptor_label` from earning the sentence;
    # it does nothing about one RIDING ALONG with a key that CAN write, because
    # `any(...)` is then satisfied by the other key. Measured on a completed record
    # whose stored label is `user_supplied`, on BOTH ingresses:
    #
    #     POST /answers {"series": <byte-identical>, "descriptor_label": "A BRAND NEW LABEL"}
    #       -> 200 changed=False, "the submitted value was identical",
    #          stored label AFTER: user_supplied
    #     POST /edit    {"series": <identical>, "descriptor_label": "NEW LABEL 2"} -> same
    #
    # So the label was neither identical, nor stored, nor compared — and the ride-along
    # UNRECOGNISED key, one key further over, is correctly suppressed by `and not
    # dropped` at the call sites. This is that half's blind spot: a RECOGNISED inert key
    # never enters `dropped`. `descriptor` present alongside is the boundary and is
    # deliberately still allowed to claim the comparison, because then the label IS
    # written onto the block the descriptor builds, so a byte-stable document really
    # does mean the submitted values were the stored ones.
    if "descriptor_label" in named and "descriptor" not in named:
        return False
    return all(_correction_is_storable(k, apply_shape[k]) for k in named) and all(
        _correction_is_storable(uri, sha) for uri, sha in shas.items()
    )


def _refuse_unstorable_answer(
    apply_shape: dict,
    answers_by_id: dict | None = None,
    *,
    size: bool = True,
    shape: bool = True,
) -> JSONResponse | None:
    """``422 invalid_field_value`` for an ANSWER the store cannot keep, or ``None``.

    THE DEFECT THIS CLOSES: ``/answers`` APPLIED NO SIZE AND NO DEPTH BOUND WHILE
    ``/edit`` APPLIED BOTH, so the answering path — the one a scientist and an MCP agent
    actually use to fill a record in — was the least-guarded write ingress in the
    application. Measured by an independent security review on 2026-08-24, over HTTP,
    against a record created through this application's own Create Experiment path:

    * a 20 MiB ``qc.evidence`` was ``200`` and PERSISTED on ``POST /answers`` (the
      workspace file grew to ~42 MB — roughly 2x amplification through ``block_evidence``
      and ``answer_log``), and ``422 invalid_field_value`` on ``POST /edit``. Same value,
      same field, same record, two answers.
    * a 700-deep ``descriptor`` drove ``RecursionError`` out of
      ``isaac_records.complete``'s ``copy.deepcopy`` as a bare ``HTTP 500`` from the truth
      core; depth 400 was accepted and stored. ``/edit`` returned the typed ``422``.

    There is no global body-size middleware in this application, so neither had any other
    backstop. The ``qc`` half is this branch's own doing: ``qc`` was not forwarded at all
    on ``main`` (see :func:`_answers_to_apply_shape`), so adding the forward added the
    ingress — and gave it the weaker screen of the two.

    WHY A ROUTE-LEVEL SCREEN RATHER THAN A GUARD IN THE TRUTH CORE. ``src/isaac_records``
    is the protected path (CLAUDE.md §13) and a depth guard there would change what
    ``apply_answers`` does for every caller, including the CLI and the exporter. The
    condition is an INGRESS condition — "this application cannot survive storing and
    re-rendering this" — and every other instance of it in this module is enforced at the
    route. CLAUDE.md §15 already records this exact shape ("a wrong-typed structured
    answer used to return HTTP 500 from the truth core") as something a typed 422 should
    close, and this is the same close, at the same layer.

    ~~WHAT IT DELIBERATELY DOES NOT DO: it does not apply the SHAPE predicates
    :func:`_correction_is_storable` applies. A wrong-TYPED answer must keep taking the
    module's existing "not applied -> the blocker stays open" path, which is what
    ``test_answers_wrong_type.py`` pins and what the record ``/edit`` route's own comment
    calls out as the reason it did not extend its screen here.~~ — **WITHDRAWN
    2026-08-25, and struck rather than deleted because the reasoning was not wrong, it
    was incomplete about what the caller can see.** It rested on *"the response already
    tells the caller the question was not answered"*, which is true of the ``pending``
    list and FALSE of the sentence beside it: ``invalidation.reason`` read *"the
    submitted value was identical; nothing was invalidated"*, so the response told the
    caller both that the question was open and that its answer was already stored. An
    independent end-to-end verification of the MCP surface followed that pair
    mechanically into a closed loop (``changed: false`` reads as "already stored" ->
    ``correcting: true`` -> ``422 not_yet_answered`` -> back to this operation), and no
    message anywhere in the cycle said the value's SHAPE was rejected. CLAUDE.md §11
    already recorded the typed ``422`` for a wrong-typed structured answer as *"a
    deliberate follow-up, not an oversight"*; this is that follow-up.

    SO IT NOW APPLIES BOTH HALVES, and the second half is asked of the RAW answers
    rather than of ``apply_shape``. That is not a stylistic choice: an off-enum ``qc``
    never reaches ``apply_shape`` at all (``_answers_to_apply_shape`` screens it out on
    the answering path, for reasons its own comment gives), so a screen over the shaped
    body could not see the single most reported instance of this defect.

    THE SHAPE HALF IS NARROWED TO :data:`_SHAPE_SCREENED_ANSWER_KEYS`, which is three of
    the five named keys. That constant carries the argument for the two it excludes, and
    a malformed asset sha256 is excluded for a further reason worth stating here: it is
    the one case where the ``200``-with-the-blocker-still-open behaviour is not merely
    tolerated but SHIPPED — ``GuidedCompletion`` renders "That answer was not applied …
    nothing was invented in its place" for it, and a browser mutation spec asserts the
    status is ``200`` precisely so the client cannot lean on an error. Refusing it is a
    frontend change as much as a backend one, so it stays a ``200`` — but its no-op
    reason no longer claims the value was identical, because
    :func:`_resubmission_was_identical` asks the same predicate and answers ``False``.

    ``size``/``shape`` SELECT THE HALVES, AND THEY EXIST BECAUSE THE RECORD ROUTE MUST
    RUN THEM ON EITHER SIDE OF A DIFFERENT REFUSAL. Adding the shape half made this
    function fire where only the size half used to, and it PREEMPTED
    :func:`_refuse_run_level_on_the_record` for the same keys. Measured on a record with
    one run, over HTTP::

        {"series": "nope"}      before: 409 belongs_to_a_run (names the run + answer_at)
                                 after: 422 invalid_field_value, no answer_at
        {"descriptor": "nope"}  before: 409                     after: 422
        {"series": <valid>}     both:   409   (control)

    That is a regression the slice adding the shape half argued AGAINST in its own
    words: it chose the narrow unrecognised-key rule precisely because *"a refusal that
    misdirects is worse than one that says nothing"*, citing this very ``409`` for these
    very keys — and then preempted it from the other side.

    SO THE RECORD ROUTE ORDERS THEM ``size`` -> ``409`` -> ``shape``, and each position
    is argued:

    * the SIZE half stays first. A value that can be stored at NO level must not be
      answered with "send it to the run", because the run refuses it with this same
      ``422``; and it is the one refusal that must precede anything that WALKS the
      value, since ``apply_answers`` deep-copies it (the measured ``RecursionError``).
    * the ``409`` comes next. For a run-owned key on a record that has runs, "this
      belongs to run X, answer it there" is strictly more useful than "that value is
      the wrong shape for a level that no longer owns it".
    * the SHAPE half comes last, so it answers only for a key the ``409`` did not claim.

    ``qc`` IS THE ONE KEY THIS ORDERING DOES NOT MOVE, and it is stated rather than left
    to be discovered: an off-enum ``qc`` never reaches ``apply_shape`` at all
    (``_answers_to_apply_shape`` screens it out on the answering path), so
    ``_run_level_keys_in`` — which reads the SHAPE — cannot see it and the ``409``
    cannot fire for it wherever the halves run. The shape half reads the RAW body, which
    is exactly why it still can. So on one record a malformed ``series`` is redirected
    and a malformed ``qc`` is refused. Teaching the ``409`` to read the raw body would
    change what ``belongs_to_a_run`` means and is its own slice.

    The RUN route keeps both halves in one call: it has no ``409`` to preserve.

    THE ERROR CODE IS ``/edit``'s, and that is a decision rather than convenience: it is
    the same condition on the same field set, and a client that already branches on
    ``invalid_field_value`` should not need a second code to learn that a value it sent
    is too big. The MESSAGE differs, because ``/edit``'s says "The stored value is
    unchanged" — true there, and false here, where the field may never have held a value
    at all. It says instead that the question is still open, which is what the caller
    needs to know and is exactly what the refusal guarantees.
    """
    offending: list[str] = []
    for key in ([
        key
        for key, value in apply_shape.items()
        if key not in ("timestamp", "asset_sha256") and not _value_fits_the_store(value)
    ] + [
        uri
        for uri, sha in (apply_shape.get("asset_sha256") or {}).items()
        if not _value_fits_the_store(sha)
    ] if size else []):
        if key not in offending:
            offending.append(key)
    # THE SHAPE HALF, over the RAW answers. Deduplicated against the size half above
    # because `_correction_is_storable` asks `_value_fits_the_store` first, so an
    # oversized AND wrong-shaped value would otherwise be named twice in `keys` — and
    # `keys` is a list a client is told names every offending key, not a bag.
    for key in _SHAPE_SCREENED_ANSWER_KEYS if shape else ():
        value = (answers_by_id or {}).get(key)
        if value in (None, ""):
            continue  # a blank answer is not an answer; it is dropped, as it always was
        if not _correction_is_storable(key, value) and key not in offending:
            offending.append(key)
    if not offending:
        return None
    return JSONResponse(
        status_code=422,
        content={
            "error": "invalid_field_value",
            "key": offending[0],
            "keys": offending,
            # NAMES NO CAUSE, for the reason the `/edit` refusal's own comment gives at
            # length: a sentence naming a cause was measured being served verbatim about
            # a key it did not describe. `key`/`keys` say WHICH value was refused;
            # nothing here is entitled to say why.
            # ~~"so nothing was written and the question is still open"~~ — TRUE OF THE
            # CASE THIS REFUSAL WAS WRITTEN FOR AND FALSE OF THE CASE THE SHAPE HALF
            # ADDED. A value can be unstorable at a key whose question is already
            # CLOSED, and telling that caller their question is still open is a second
            # false claim in a refusal added to remove one. It now says both halves
            # conditionally-free: whatever was stored is still stored, and whatever was
            # open is still open.
            "message": (
                "This answer is not a shape the record can store, so nothing was "
                "written: any value the record already held for it is unchanged, and "
                "any question it would have answered is still open."
            ),
        },
    )


def _answers_to_apply_shape(
    answers_by_id: dict, draft: dict, timestamp: str, *, edit_only: bool = False
) -> dict:
    """Translate UI answers (keyed by blocker id/about) into ``apply_answers`` input.

    Only values literally present are forwarded; blank/missing answers are dropped, so the
    core never invents. Asset blockers key on their URI;
    ``series``/``descriptor``/``edge``/``qc`` key on their kind name.

    ``qc`` WAS ABSENT FROM THIS LIST UNTIL 2026-08-19, and the omission was not cosmetic.
    A ``qc`` blocker is raised whenever the source supplied no QC verdict to read
    (``extract.draft_builder``) — independently of whether a series is present; it is the
    export REFUSAL that is series-conditional (``draft_validator``). Conflating the two,
    as an earlier revision of this paragraph did, makes the blocker sound narrower than it
    is. It was the ONE blocker no request could answer — so a record created through this application's own
    Create Experiment path could have every other question answered and still never
    export, refused by the draft validator with *"measurement has series but qc verdict
    has no evidence"*. The five canonical seeds hid it: their drafts are built offline
    with ``qc`` already present. The core branch always existed and always validated the
    enum (``complete.apply_answers`` / ``apply_corrections``); only the forward was
    missing. See :func:`isaac_records.complete.is_qc_shaped` for why the storability rule
    lives there rather than being restated here.

    ``edit_only`` NARROWS THE ASSET KEY SET TO ASSETS THAT ACTUALLY EXIST, and it exists
    because the union below was measured answering **200 about a write that could not
    happen** — the same defect class the sha256 guard above was added to close, on the same
    route and the same key. Measured on the correction path with a PERFECTLY WELL-FORMED
    hash for a still-PENDING asset uri: ``200``, ``rev`` unmoved, nothing stored, and
    ``invalidation.reason`` reading "the submitted value was identical; nothing was
    invalidated" — which names a cause that is false twice over, because the value was
    neither identical nor ever stored.

    Why it cannot be stored: :func:`apply_corrections` iterates ``draft["assets"]``, and a
    pending asset is by construction not in it — :func:`apply_answers` is what CREATES the
    asset entry from the blocker. So on the correction path a pending uri names no editable
    field at all, and this route's existing "no recognised editable field" refusal is the
    honest answer. It is deliberately NOT the ``invalid_field_value`` refusal: the VALUE
    was fine, and telling the reader "the field still holds the value it held before" would
    be a third false claim about a field that holds no value yet.

    ``POST /answers`` keeps the union unchanged — there a pending uri is precisely the key
    the route is supposed to accept, and that direction is pinned by test.
    """
    # THE URI SET IS :func:`_answer_asset_uris`', not a local comprehension, so the
    # refusal that decides which URI keys are RECOGNISED and this function, which
    # decides which are FORWARDED, cannot disagree. `edit_only` narrows it to the
    # stored ones; the argument for that is the paragraph above.
    asset_uris = _answer_asset_uris(draft, edit_only=edit_only)
    out: dict = {"timestamp": timestamp, "asset_sha256": {}}
    for key, value in (answers_by_id or {}).items():
        if value in (None, ""):
            continue
        if key in asset_uris:
            out["asset_sha256"][key] = value
        elif key == "qc":
            # SCREENED ON THE `/answers` PATH ONLY, and the asymmetry is deliberate in
            # both directions.
            #
            # WHY `/answers` SCREENS: it does not run `_correction_is_storable`; it
            # relies on the core leaving an unusable answer's blocker OPEN, which
            # `apply_answers` does for an off-enum `status`. It did NOT do that for the
            # EVIDENCE note — the qc branch assigned any truthy `evidence` straight onto
            # `measurement.qc.evidence`, so `{"status": "valid", "evidence": {...}}`
            # cleared the blocker and stored a dict where the schema declares a string.
            # Screening here is what stops a 200 about a record official validation
            # would later reject.
            #
            # WHY `/edit` DOES NOT: that path DOES screen, one layer down, and it needs
            # the key to arrive in order to do so. Screening it away here made
            # `_has_correction_target` answer False, so an unusable verdict came back as
            # `unrecognized_field` — "this application does not know that field" — when
            # the field is recognised and only the VALUE is unusable. That distinction
            # is this route's own stated doctrine, and getting it wrong tells a
            # scientist to look for a misspelling that is not there.
            #
            # THE `/answers` SCREEN IS NOW BELT-AND-BRACES RATHER THAN THE ONLY GUARD,
            # and it is kept for that reason. Since 2026-08-25 both answers routes run
            # `_refuse_unstorable_answer` over the RAW body ahead of this call, so an
            # off-enum verdict is refused with a typed `422` before the mapper is
            # reached and this branch's `is_qc_shaped` no longer decides any HTTP
            # outcome. Removing it would make this function's own behaviour depend on
            # its callers ordering two things correctly, which is how the run path
            # ended up without a value screen at all.
            if edit_only or is_qc_shaped(value):
                out[key] = value
        elif key in _NAMED_ANSWER_KEYS:
            out[key] = value
        # A key outside `_NAMED_ANSWER_KEYS` and outside `asset_uris` is dropped here —
        # never invented into the draft. On the two ANSWERS routes it no longer reaches
        # this point: `_refuse_a_body_that_names_nothing_answerable` has already refused it by name.
        # On the two EDIT routes the drop is still the live behaviour, deliberately (see
        # that refusal's docstring for why the asymmetry is scoped rather than accidental).
    return out


#: The shaped-answer keys whose value lands in a RUN-LEVEL draft block. Derived from
#: `workspace.block_level` rather than listed, so a block that changes level cannot
#: leave a stale copy of the rule here.
#:
#: ``edge`` IS EXEMPT, AND THIS ENTRY HAS NOW BEEN WRONG IN BOTH DIRECTIONS. Both
#: mistakes are recorded because the second was made while fixing the first.
#:
#: **First version — exempt, on a false premise.** It said ``implicit`` is merged onto
#: EVERY run, so an edge answered on the record always reaches it. That is not what
#: ``resolved_run_draft`` does: ``inherit=not _diverges_from_experiment(resolutions)``,
#: and one override — even a no-op one — withholds all of it. Measured: ``POST /edit
#: {"edge": "L3"}`` answering **200** with ``changed_fields: ['edge']`` against a run
#: whose composed ``implicit`` was ``[]``.
#:
#: **Second version — refused, which was WORSE.** Refusing it on the record made ``edge``
#: answerable by NO route at all: the run-level route accepts the key and writes it into
#: the RUN's ``implicit``, where nothing reads it either (measured: ``200``,
#: ``changed: false``, the composed ``implicit`` still holding the record's value). And
#: the refusal body then made two false claims about it — that there is an operation that
#: can take the answer, and that answering on the record writes a value no exported
#: record reads. For a non-diverging run the second is simply untrue: inheritance was
#: ACTIVE in the measurement. Trading a 200-that-writes-nothing for a 409 pointing at a
#: 200-that-writes-nothing is not a fix.
#:
#: **So it is exempt again, with the truth stated rather than a premise assumed.** An
#: edge answered on the record reaches every run that holds the record's values, and
#: does NOT reach a run that has diverged at any experiment-level address. That gap is a
#: property of ``_merge_implicit`` — a derivation can outlive the value it was derived
#: from, which is why that function withholds — and it is not something this refusal can
#: close. Closing it means either making ``edge`` a run-level block or giving
#: ``_merge_implicit`` a per-address rule, and both are their own slice.
#:
#: No UI path sends ``edge`` (no ``edge`` blocker exists — ``draft_builder`` emits a null
#: ``implicit`` entry, never a pending one), so the exemption's cost falls only on a
#: direct API or MCP caller, and it is a 200 that reaches the runs that can receive it.
#:
#: **THIRD CORRECTION, 2026-08-24: "an edge answered on the record reaches every run that
#: holds the record's values" IS TRUE ONLY OF A RECORD THAT HAS AN EDGE DERIVATION, and
#: the sentence above asserted it of every record.** An independent security review
#: measured the gap it left. ``complete.apply_answers`` and ``complete.apply_corrections``
#: both write ``edge`` only INTO an existing ``implicit[]`` entry whose ``about`` is
#: ``"edge"``; ``draft_builder`` is what emits that entry, and a record created through
#: ``POST /api/experiments`` has no ``implicit`` block at all. So on a created record the
#: answer reached NO run, because it was never stored — and the response said ``changed:
#: false`` with the reason *"the submitted value was identical; nothing was invalidated"*,
#: a claim that is false twice over and is the exact defect this branch fixed for
#: ``series``, ``qc``, ``descriptor`` and a pending asset uri.
#:
#: The exemption STANDS — it was right about the record that motivated it, and refusing
#: unconditionally was already tried and was worse. What is added is a screen on the one
#: fact that decides whether the write can happen at all:
#: :func:`_refuse_edge_with_nothing_to_confirm`, applied on all four write paths. A
#: record whose draft carries an edge derivation is unaffected; a record with nothing to
#: write into is told so instead of being told its value was identical.
#:
#: `timestamp` is bookkeeping, not an answer.
_RUN_LEVEL_ANSWER_BLOCK = {
    "series": "series",
    "qc": "qc",
    "descriptor": "descriptors_outputs",
    "descriptor_label": "descriptors_outputs",
}

#: Answer keys that would be run-owned but live outside a top-level run-level block.
#: EMPTY, and the long note above says why: the only candidate was ``edge``, and
#: refusing it made it answerable by no route at all. The tuple is kept rather than
#: deleted so a future key of that shape has somewhere to go, with the argument for
#: why it belongs there written directly above it.
_RUN_LEVEL_ANSWER_KEYS_WITHOUT_A_BLOCK: tuple[str, ...] = ()


def _run_level_keys_in(apply_shape: dict) -> list[str]:
    """The keys in this shaped body that a RUN owns rather than the record.

    Asset hashes count, because ``assets`` is a run-level block: an asset sha answered
    on the record after a run exists lands in a block ``resolved_run_draft`` never reads.
    """
    keys = sorted(
        [
            key
            for key, block in _RUN_LEVEL_ANSWER_BLOCK.items()
            if key in apply_shape and ws.block_level(block) == ws.LEVEL_RUN
        ]
        + [key for key in _RUN_LEVEL_ANSWER_KEYS_WITHOUT_A_BLOCK if key in apply_shape]
    )
    if apply_shape.get("asset_sha256") and ws.block_level("assets") == ws.LEVEL_RUN:
        keys.extend(sorted(apply_shape["asset_sha256"]))
    # SORTED, so the refusal body is stable. It was in `_RUN_LEVEL_ANSWER_BLOCK`'s
    # declaration order, which is deterministic but arbitrary — a client comparing
    # `keys` would have been comparing against a literal nobody chose. Asset URIs are
    # appended after the named keys and sorted among themselves, so the two kinds stay
    # visually separable in a message a person reads.
    return keys


#: The operation that ANSWERS an open blocking question, one entry per LEVEL. They are
#: TEMPLATES rather than interpolated URLs, and the concrete ids travel beside them in
#: their own response keys — the convention every operation pointer in this module
#: already follows (``ordinary_scope_required``'s ``operation``,
#: ``tutorial_scope_forbidden``'s, and this file's own ``belongs_to_a_run``).
#:
#: THEY ARE CONSTANTS BECAUSE THE SAME TWO STRINGS ARE NOW CITED BY TWO DIFFERENT
#: REFUSALS, and one of them was measured pointing at the wrong level. ``belongs_to_a_run``
#: sends a run-owned key from the record to the run; ``not_yet_answered`` sends an
#: unanswered key to whichever level raised it. A caller that follows either one must land
#: somewhere that accepts the request, so the two must name the same operations by the same
#: text — two copies of a URL is how one of them ends up stale.
_ANSWERS_OPERATION_RECORD = "POST /api/experiments/{experiment_id}/answers"
_ANSWERS_OPERATION_RUN = "POST /api/experiments/{experiment_id}/runs/{run_id}/answers"

#: The operation that CORRECTS an already-answered field, one entry per LEVEL — the
#: exact counterparts of the two above, and constants for the same reason: two copies
#: of a URL is how one of them ends up stale. They are what ``already_answered``'s
#: ``answer_at`` names, which is the mirror image of what ``not_yet_answered`` names.
_EDIT_OPERATION_RECORD = "POST /api/experiments/{experiment_id}/edit"
_EDIT_OPERATION_RUN = "POST /api/experiments/{experiment_id}/runs/{run_id}/edit"

#: The ``422`` BOTH answers operations serve. RENAMED FROM ``_R_ALREADY_ANSWERED``, whose
#: name had outlived its scope: it described ONE of the refusals in it, and the block now
#: describes FIVE — ``confirmation_required``, ``no_derivation_to_confirm``,
#: ``unrecognized_field``, ``invalid_field_value`` and ``already_answered``, plus the
#: framework's own body-validation shape. A constant named after its first member is how
#: the next refusal gets added without anyone noticing the name stopped covering the
#: contents; ``_R_CORRECTION_REFUSED`` — whose own note records "the record's ``422``
#: enumerated three refusals while the route performed four" — is the sibling this now
#: matches.
#:
#: THE SCHEMA REF IS PART OF THE CONSTANT for the reason :data:`_R_NOT_YET_ANSWERED`
#: states: FastAPI skips generating its own ``422`` the moment a route declares one,
#: silently stripping the ``HTTPValidationError`` ref that
#: ``test_operations_with_parameters_keep_the_validation_error_schema`` pins for every
#: operation with a parameter or a body. That framework shape stays reachable on both
#: answers operations (a request body that is not a JSON object), so it travels here.
#:
#: ``invalid_field_value`` IS NAMED HERE FOR THE SAME REASON ``already_answered`` WAS:
#: the operation performs it and the published contract did not describe it. It was
#: added to both answers operations on 2026-08-24, when an independent security review
#: measured that ``/answers`` applied no size and no depth bound while ``/edit`` applied
#: both — see :func:`_refuse_unstorable_answer`. Adding the behaviour without adding the
#: sentence would repeat exactly the gap :data:`_R_CORRECTION_REFUSED` was written to
#: close, where "the record's ``422`` enumerated three refusals while the route performed
#: four".
_R_ANSWER_REFUSED: dict = {
    422: {
        "description": (
            "Either the request body failed framework validation (the "
            "`HTTPValidationError` shape below), or `confirmed_by_user` was not "
            "`true` (`confirmation_required`), or `no_derivation_to_confirm`, or "
            "`unrecognized_field`, or `invalid_field_value`, or "
            "`already_answered`.\n\n"
            "`unrecognized_field` — the body named a key that is not one of this "
            "operation's answer keys and not an asset URI this record knows. Nothing "
            "was written and no question moved. The body is "
            "`{error, experiment_id, key, keys, message}`, plus `run_id` on the "
            "run-level operation, and `keys` names EVERY unrecognised key. **THIS IS "
            "A CHANGE OF CONTRACT, DECLARED RATHER THAN SLIPPED IN.** These operations "
            "used to state that an unrecognised key *is ignored rather than invented*, "
            "and they silently dropped it — which made a mistyped key indistinguishable "
            "from an accepted one, because the resulting `200` explained itself as "
            "*\"the submitted value was identical\"* about a key the record had never "
            "held. ~~A key is now either acted on or refused by name.~~ "
            "**OVERSTATED, AND SCOPED HERE RATHER THAN DELETED** \u2014 a key is acted "
            "on, refused by name, or, WHEN AT LEAST ONE OTHER KEY IN THE SAME BODY WAS "
            "RECOGNISED, dropped on a `200` that does not name it. Measured: `{\"qc\": "
            "<valid>, \"sample.material.nmae\": \"Fe2O3\"}` answers `200` with "
            "`changed_fields: [\"qc\"]`, and the mistyped key appears nowhere in the "
            "response. What IS guaranteed for that key, and is the half this change "
            "actually built: **the `200` withholds the identical-value reason whenever "
            "anything was dropped**, so no sentence in it can be read as acknowledging "
            "the key that vanished. Naming dropped keys in the body needs a new response "
            "field, which is the frontend's contract too, so it belongs to a slice that "
            "can change both. A BLANK value "
            "(`null` or `\"\"`) is still dropped at any key, recognised or not: a blank "
            "answer is not an answer. The correction operations are deliberately "
            "unchanged and still tolerate a ride-along key.\n\n"
            "`no_derivation_to_confirm` — the body named `edge`, and this record "
            "carries no absorption-edge derivation for the answer to confirm. An edge "
            "is recorded as a confirmation of a value this application derived from a "
            "source document, and no operation creates that derivation, so there was "
            "nothing to write into and nothing was written. The body is "
            "`{error, experiment_id, key, keys, message}`, plus `run_id` on the "
            "run-level operation. It deliberately names no alternative operation, "
            "because there is none. The official ISAAC record has no edge field, so no "
            "exported record is missing a value because of this refusal.\n\n"
            "`invalid_field_value` — a recognised key carried a value this "
            "application cannot store: too large, nested too deeply, not renderable as "
            "JSON (`NaN`, `Infinity`, a lone surrogate), **or not a shape the record "
            "can hold at that key**. Nothing was written, any value the record already "
            "held is unchanged, and any question this would have answered is still "
            "open. The body is `{error, key, keys, message}`, where `keys` names EVERY "
            "offending key and `message` deliberately states no cause. It is the same "
            "code the correction operations serve for the same condition, deliberately: "
            "a client that already branches on `invalid_field_value` should not need a "
            "second code to learn that a value it sent is too big.\n\n"
            "~~A wrong-TYPED value is NOT this refusal — it is dropped by the core and "
            "its question is reported still open in the `200`, which is the behaviour "
            "this operation has always had.~~ **WITHDRAWN 2026-08-25.** A wrong-typed "
            "`series`, `qc` or `descriptor` IS this refusal now. The old behaviour "
            "relied on the `200`'s question list to tell the caller nothing landed, "
            "while the `invalidation.reason` beside it said the submitted value was "
            "already stored — so the two halves of one response contradicted each "
            "other, and a client that followed the documented remedy for an "
            "already-stored value was sent to the correction operation and refused "
            "there with `not_yet_answered`. Three named keys are screened: `series`, "
            "`qc` and `descriptor`. A wrong-typed `descriptor_label` or `edge` is NOT "
            "screened (the core stores those rather than declining them, so refusing "
            "them would be a new refusal, not a corrected report), and a MALFORMED "
            "asset sha256 is deliberately still a `200` with the blocker left open — "
            "but its `invalidation.reason` no longer claims the value was "
            "identical.\n\n"
            "`already_answered` \u2014 the body named a field whose question is already "
            "CLOSED and supplied a value DIFFERENT from the confirmed one, which this "
            "operation would have discarded. Nothing was written, the stored value is "
            "unchanged, and the revision did not move. The body is "
            "`{error, experiment_id, keys, answer_at, message}`, plus `run_id` on the "
            "run-level operation, and `keys` names EVERY offending key rather than the "
            "first.\n\n"
            "**RESUBMITTING THE IDENTICAL VALUE IS STILL A SUCCESS** and is deliberately "
            "not this refusal: a client may retry a request it is unsure landed, and "
            "gets `200` with `changed: false` and an unmoved revision, exactly as "
            "before. The refusal fires only where the two values differ, which is the "
            "only case in which anything the caller sent was lost.\n\n"
            "`answer_at` NAMES THE CORRECTION OPERATION AT THE LEVEL THIS REFUSAL WAS "
            "RAISED AT \u2014 the record's edit operation for a refusal on the record, "
            "the RUN's for a refusal on a run. It is a template, and "
            "`experiment_id`/`run_id` carry the concrete ids, exactly as "
            "`not_yet_answered` and `belongs_to_a_run` do. It is always present here "
            "and is provably actionable rather than plausibly so \u2014 see the "
            "refusal's own notes for why `/edit` cannot refuse what this redirects."
        ),
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/HTTPValidationError"}
            }
        },
    },
}




def _refuse_run_level_on_the_record(exp, apply_shape: dict) -> JSONResponse | None:
    """Refuse a run-owned answer sent to the RECORD, once the record has runs.

    THE DEFECT THIS CLOSES, measured over HTTP by an independent review. ``series``,
    ``qc``, ``assets`` and ``descriptors_outputs`` are run-level blocks, so
    ``resolved_run_draft`` reads them off the RUN. Once a run exists, an answer written
    into ``exp.draft`` reaches no exported record — and nothing said so::

        qc = compromised + "Beam dropped during scan 3; spectrum unusable."
        POST /runs                                        -> 201
        POST /edit {"qc": {"status": "valid", ...}}        -> 200, status ready_to_export
        POST /export                                      -> ok: true
        ON DISK measurement.qc = {"status": "compromised", "evidence": "Beam dropped …"}

    The correction was accepted, reported as applied, and published nothing; the record
    kept a verdict its own sidecar then contradicted, and ``artifact.state`` read
    ``current``. A 200 about a write that could not happen is the exact shape this route
    already refuses for a pending asset uri; this is the same refusal, one entity up.

    It names the run and the route that CAN take the answer, because refusing without
    that would leave a multi-run record unfinishable — which is a different defect, not
    a fix.
    """
    if not exp.runs:
        return None
    offending = _run_level_keys_in(apply_shape)
    if not offending:
        return None
    return JSONResponse(
        status_code=409,
        content={
            "error": "belongs_to_a_run",
            "experiment_id": exp.id,
            "keys": offending,
            "runs": [
                {"run_id": run.id, "run_label": run.label} for run in exp.sorted_runs()
            ],
            "answer_at": _ANSWERS_OPERATION_RUN,
            "message": (
                "This record has runs, and each run is a record of its own. A spectrum, "
                "a QC verdict, a descriptor and an asset hash belong to the run that "
                "measured them, so answering them here would write a value no exported "
                "record reads. Send them to the run instead. Nothing was written."
            ),
        },
    )



@router.post(
    "/experiments/{experiment_id}/answers",
    tags=[TAG_DRAFTS],
    summary="Answer a Record's Blocking Questions",
    description=(
        "Applies caller-supplied answers to this draft's open blocking questions "
        "and returns the refreshed question list, the record's status, its new "
        "revision metadata, the derived workflow, and which downstream steps the "
        "change reopened.\n\n"
        "Requires `confirmed_by_user: true` and the record's current `ETag` in "
        "`If-Match`. A BLANK answer is dropped rather than invented, so a "
        "submission carrying only blanks is a no-op: it is not logged and does not "
        "advance the revision. ~~Blank and unrecognised answers are dropped~~ — an "
        "UNRECOGNISED KEY is now refused with `422 unrecognized_field` instead of "
        "being dropped, and a `series`, `qc` or `descriptor` value the record "
        "cannot hold is refused with `422 invalid_field_value`. Both used to be "
        "absorbed into a `200` whose `invalidation.reason` read *\"the submitted "
        "value was identical\"* about a value that had neither been stored nor been "
        "compared. **Resubmitting a value the record already holds is still a "
        "`200` with an unmoved revision**, so retrying a call you are unsure "
        "landed is still safe."
        "\n\n" + _BOUNDED_PENDING_PARAGRAPH
    ),
    response_description=(
        "The refreshed blocking questions, status, revision metadata, workflow, "
        "and the downstream invalidation, with the new `ETag`.\n\n"
        "ONE LIMIT THAT ONLY A `200` CAN CARRY, AND IT IS STATED HERE BECAUSE A "
        "CALLER WHO SUCCEEDS NEVER READS THE `409`. On a record that has runs, "
        "`edge` is answerable here and is deliberately not among the keys the "
        "`409` refuses: it lives in the record's implicit derivations, which every "
        "run holding the record's values inherits, so answering it here does reach "
        "those runs. A run that has recorded ANY override — even one that changed "
        "nothing — inherits none of them, so for that run this write reaches no "
        "exported record. `changed_fields` reporting `edge` is a true statement "
        "about the record's own draft and is not a claim about any run."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        **_R_PRECONDITION,
        **_R_BELONGS_TO_A_RUN,
        # DECLARED, because it was not. This operation already performed
        # `confirmation_required` and now performs `already_answered`, and neither was
        # described in the published contract — the same gap `_R_NOT_YET_ANSWERED`
        # records for its own refusal, which "reached no generated OpenAPI document,
        # and therefore no machine client that reads the contract before calling it."
        **_R_ANSWER_REFUSED,
    },
)
def post_answers(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"confirmed_by_user\": true, \"answers\": {<key>: <value>}}`. The "
            "keys come from `GET /api/experiments/{experiment_id}/pending`. "
            "Omitting `confirmed_by_user: true` is rejected with `422`; an "
            "UNRECOGNISED key is refused with `422 unrecognized_field` (~~is ignored "
            "rather than invented~~, which was true and unhelpful — the drop was "
            "silent and the resulting `200` claimed the value was identical); a "
            "`series`, `qc` or `descriptor` value the record cannot hold is refused "
            "with `422 invalid_field_value`; and a recognised key whose question is "
            "already closed, submitted with a DIFFERENT value, is refused with `422 "
            "already_answered`."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The record's current `ETag`, exactly as a read operation "
            "returned it."
        ),
    ),
):
    # Cheap existence pre-check OUTSIDE the lock so a bogus/non-existent id never
    # creates a permanent entry in the never-evicting per-record lock map (bounds
    # it to ids that actually resolve to a record).
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    # The per-record lock serialises the entire load->precondition->mutate->save
    # compare-and-swap; the experiment is loaded FRESH inside the lock so two
    # writers holding the same token cannot both succeed.
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        if body.get("confirmed_by_user") is not True:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "confirmation_required",
                    "message": "confirmed_by_user must be true to apply answers.",
                },
            )
        err = _check_if_match(if_match, exp)
        if err is not None:
            return err
        # Capture the PRE-mutation workflow so the invalidation can report the
        # reopen DELTA (which completed steps regressed) after applying answers.
        pre_steps = _workflow_for(exp)["ordered_steps"]
        # The answer keys we are about to forward (non-blank, recognised). On a
        # real change these are the fields written; on a no-op nothing is written.
        submitted_fields = [
            k for k, v in (body.get("answers") or {}).items() if v not in (None, "")
        ]
        timestamp = _now_iso()
        # WHAT THE MAPPER WILL DROP, computed BEFORE it drops it — a route cannot report
        # honestly about a key it can no longer see. It walks keys only, never values, so
        # it does not front-run the depth guard below (the one refusal that must precede
        # anything that walks a submitted value).
        dropped = _dropped_answer_keys(
            body.get("answers") or {}, exp.draft, edit_only=False
        )
        refusal = _refuse_a_body_that_names_nothing_answerable(
            body.get("answers") or {}, dropped, {"experiment_id": exp.id}
        )
        if refusal is not None:
            return refusal
        apply_shape = _answers_to_apply_shape(body.get("answers") or {}, exp.draft, timestamp)
        # FIRST OF THE REFUSALS, AND ONLY ITS SIZE HALF — the SHAPE half runs after the
        # `409` below, because it preempted it. See `_refuse_unstorable_answer`.
        #
        # THE ORDER IS ARGUED RATHER THAN INHERITED.
        # `belongs_to_a_run` below sends a run-owned key to the run's own operation, which
        # is the more useful answer for a value that could be stored SOMEWHERE. This one
        # is for a value that can be stored NOWHERE — too big, too deep, or unrenderable
        # at any level — so answering `409 go to the run` first would send a compliant
        # client on a round trip that ends in this same `422`. It is also the cheapest of
        # the three and the only one that must run before anything WALKS the value:
        # `apply_answers` deep-copies it, which is where the measured `RecursionError`
        # came from.
        refusal = _refuse_unstorable_answer(apply_shape, shape=False)
        if refusal is not None:
            return refusal
        refusal = _refuse_run_level_on_the_record(exp, apply_shape)
        if refusal is not None:
            return refusal
        # THE SHAPE HALF, DELIBERATELY AFTER THE `409`, and the split is the fix for an
        # ordering regression this branch introduced. Running both halves together made
        # `{"series": "nope"}` on a record with one run answer `422 invalid_field_value`
        # where it used to answer `409 belongs_to_a_run` naming the run and the operation
        # that CAN take the answer — a refusal that misdirects, replacing one that helps.
        # `_refuse_unstorable_answer`'s docstring carries the measurement and the argument
        # for each of the three positions, including why an off-enum `qc` stays a `422`
        # here no matter what this ordering does.
        refusal = _refuse_unstorable_answer(
            apply_shape, body.get("answers") or {}, size=False
        )
        if refusal is not None:
            return refusal
        # `edge` IS EXEMPT FROM THE REFUSAL ABOVE AND IS SCREENED BY THIS ONE INSTEAD.
        # The exemption is correct — an edge answered on the record reaches every run
        # that holds the record's values — but it was the only key with no screen at
        # all, so an edge answer against a draft holding no edge derivation was a 200
        # about a write that could not happen.
        refusal = _refuse_edge_with_nothing_to_confirm(
            exp.draft, apply_shape, {"experiment_id": exp.id}
        )
        if refusal is not None:
            return refusal
        # AFTER the run-level refusal, and the order is the honest one rather than an
        # arbitrary one. On a record that HAS runs, `series`/`qc`/`descriptor`/an asset
        # sha belong to the run, and `belongs_to_a_run` names the run's own answers
        # operation — a strictly more useful answer than "already answered here", where
        # "here" is a level that no longer owns the value. So this refusal is reachable
        # only on a record with no runs, which is exactly the record whose own `/edit`
        # accepts the correction it names.
        refusal = _refuse_answering_an_already_answered_key(
            exp.draft,
            body.get("answers") or {},
            timestamp,
            edit_at=_EDIT_OPERATION_RECORD,
            identifiers={"experiment_id": exp.id},
        )
        if refusal is not None:
            return refusal
        draft_before = exp.draft
        # `apply_answers` deep-copies its input and returns a NEW draft, so
        # `draft_before` is the pre-write document and stays that way.
        exp.draft = apply_answers(exp.draft, apply_shape)
        # answer_log is EXCLUDED from the rev signature: log the submission only when it
        # actually changes the authoritative draft, so an identical re-entry is neither
        # logged nor rewritten (byte-stable) and never bumps rev. save_versioned decides
        # by comparing the on-disk authoritative signature.
        exp.answer_log.append({"applied": apply_shape, "at": timestamp})
        changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another replica won the race; this change was not applied
        if not changed:
            exp.answer_log.pop()  # no-op re-entry: discard the speculative log append
        # Derived downstream invalidation (P28.2) at the post-mutation revision. A
        # byte-stable no-op reports changed=False with empty deltas and no rev bump.
        # WHAT LANDED, NOT WHAT WAS SUBMITTED. `_fields_the_shape_carries` removes keys
        # the core never received; `_fields_the_write_landed` additionally removes keys
        # it received and DECLINED — a wrong-typed `series` reported "Updated 1
        # field(s)" while the stored value was `None`. See that function for the
        # measurement. `Updated 0 field(s)` is now reachable with `changed: true`, on a
        # write whose only effect was materialising a legacy run's derived questions;
        # that sentence is literally true and is left alone rather than replaced with
        # one that would have to guess WHY the document moved.
        changed_fields = (
            _fields_the_write_landed(apply_shape, submitted_fields, draft_before, exp.draft)
            if changed
            else []
        )
        invalidation = dependencies.build_invalidation(
            changed=changed,
            changed_fields=changed_fields,
            pre_steps=pre_steps,
            post_exp=exp,
            # THE CALLER'S ANSWER TO "DID YOU COMPARE?" — see
            # `_resubmission_was_identical` for why a fully storable non-empty shape
            # plus `changed=False` IS an identical resubmission, and why an empty one
            # is not. `build_invalidation` names no cause without it.
            #
            # `and not dropped` IS THE OTHER HALF, and it is the half that closes the
            # ride-along case. A body carrying one recognised key beside one unrecognised
            # one still has the unrecognised one dropped in silence; what it must not
            # also get is a sentence saying the submitted value was already stored, which
            # a reader would apply to the key that vanished. When anything was dropped
            # this route claims nothing.
            identical=_resubmission_was_identical(apply_shape) and not dropped,
        )
        # `exp.pending()`, NOT `exp.draft` — the SAME correction `GET /pending` needed.
        # An independent review measured the consequence of missing these two: after a
        # run existed, this response came back `pending: []` while the detail response
        # said three questions remained, and `GuidedCompletion` renders "All blockers
        # resolved" on an empty list. The screen a scientist answers questions on told
        # them they were finished, about a record that could not export.
        result = _mutation_pending_response(exp, experiment_id, unit_run_id=None)
        result["status"] = exp.status()
        result.update(vc.version_fields(exp))
        result["workflow"] = _workflow_for(exp)
        result["invalidation"] = invalidation
        response.headers["ETag"] = exp.etag()
        return result


# --- 7b. edit (correct an already-answered field) -----------------------------


#: Which pending BLOCKER KIND an ``/edit`` answer key would be correcting. Assets are
#: absent because :func:`_answers_to_apply_shape` already narrows them structurally on
#: the ``edit_only`` path — ``asset_uris = stored_uris``, so an asset nothing has
#: answered is dropped before it reaches the core. ``edge`` is absent because it
#: corresponds to no blocker at all and is therefore never "unanswered".
_CORRECTABLE_KEY_KINDS: dict[str, str] = {
    "series": "series",
    "descriptor": "descriptor",
    "descriptor_label": "descriptor",
    "qc": "qc",
}

#: Where in a draft the value each of those keys corrects actually LIVES. Consulted
#: alongside the pending list, never instead of it — see
#: :func:`_refuse_correcting_an_unanswered_key` for why both are needed.
_CORRECTABLE_KEY_STORAGE: dict[str, str] = {
    "series": "series",
    "descriptor": "descriptors_outputs",
    "descriptor_label": "descriptors_outputs",
    "qc": "qc",
}

#: The refusal for correcting something nothing has answered yet.
#:
#: IT WAS DEAD FOR ITS WHOLE LIFE, and that is the reason the two constants below exist
#: rather than one. ``grep -n _R_NOT_YET_ANSWERED apps/api/isaac_api/routes.py`` returned
#: exactly ONE line — this definition — so the body :func:`_refuse_correcting_an_unanswered_key`
#: emits reached no ``responses={...}``, no generated OpenAPI document, and therefore no
#: machine client that reads the contract before calling it. Both correction operations
#: DID declare a ``422``; the record's enumerated three domain refusals and omitted this
#: one, and the run's carried only the framework's "Validation Error". So a caller could
#: read the published contract, receive ``error: not_yet_answered``, and find it described
#: nowhere.
#:
#: THE SCHEMA REF IS PART OF THE CONSTANT ON PURPOSE. FastAPI skips generating its own
#: ``422`` entry the moment a route declares one, which silently strips the
#: ``HTTPValidationError`` content ref that
#: ``test_operations_with_parameters_keep_the_validation_error_schema`` pins for every
#: operation with a parameter or a body. That framework shape is genuinely reachable on
#: both correction operations (a request body that is not a JSON object), so it is carried
#: here rather than left to whichever route happens to remember it. No JSON ``example`` of
#: the domain body is attached beside it, because an example that does not validate against
#: its own declared schema would be a second wrong answer rather than a fix.
_R_NOT_YET_ANSWERED: dict = {
    422: {
        "description": (
            "`not_yet_answered` — the body named a field that is still an OPEN "
            "question, so there was nothing to correct and nothing was written. The "
            "body is `{error, experiment_id, keys, message}`, plus `run_id` on the "
            "run-level operation, and `keys` names EVERY offending key rather than "
            "the first.\n\n"
            "`answer_at` NAMES THE OPERATION THAT CAN ACTUALLY TAKE THE ANSWER AT THE "
            "LEVEL THIS REFUSAL WAS RAISED AT — the record's answers operation for a "
            "refusal on the record, the RUN's for a refusal on a run. It is a template, "
            "and `experiment_id`/`run_id` carry the concrete ids, exactly as the "
            "`belongs_to_a_run` `409` does. It is **absent rather than wrong** when no "
            "operation can resolve the condition: a record that has runs no longer owns "
            "a spectrum, a QC verdict, a descriptor or an asset hash, so no operation on "
            "the record can answer one, and `message` says so instead. A client may "
            "therefore follow `answer_at` when it is present and must not assume it is."
        ),
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/HTTPValidationError"}
            }
        },
    },
}

#: The COMPLETE ``422`` that BOTH correction operations serve, built by merging the
#: refusal above into the three it shares with its sibling.
#:
#: ONE CONSTANT FOR TWO ROUTES, because the two refuse exactly the same four domain
#: conditions — ``confirmation_required``, ``not_yet_answered``, ``unrecognized_field``
#: and ``invalid_field_value`` — and this module already states the reason in
#: :func:`_apply_to_run`, where the ``invalid_field_value`` body is copied verbatim
#: from the record path: *"Two different messages for one condition is how a client
#: ends up branching on prose."* The same hazard applies to the two DESCRIPTIONS of
#: one condition, and it had already happened: the record's ``422`` enumerated three
#: refusals while the route performed four.
#:
#: The merge is ``**_R_NOT_YET_ANSWERED[422]`` rather than a second copy of the schema
#: ref, so the ref cannot be present on one of the two and missing on the other.
_R_CORRECTION_REFUSED: dict = {
    422: {
        **_R_NOT_YET_ANSWERED[422],
        "description": (
            "Either the request body failed framework validation (the "
            "`HTTPValidationError` shape below), or the correction was refused by "
            "this operation before anything was written, as an object whose `error` "
            "names WHICH refusal it is and whose remaining keys depend on that — "
            "`key` appears on `invalid_field_value` only, and `experiment_id` on "
            "`not_yet_answered` only. `error` is then "
            "`confirmation_required` (`confirmed_by_user` was not `true`), "
            "`unrecognized_field` (no already-answered editable field was named — "
            "including an asset whose hash is still an open question, which belongs "
            "to the answers operation), `invalid_field_value` (a recognised field "
            "carried a value the record cannot store; `key` and `keys` name the "
            "offending field(s), and `message` deliberately states no cause), "
            "`no_derivation_to_confirm` (the body named `edge` and this record carries "
            "no absorption-edge derivation for it to confirm — see the answers "
            "operation for the full description; it is the same refusal, because it is "
            "the same structural fact about the draft), or "
            "`not_yet_answered`, described next. Nothing is written on any of "
            "them.\n\n" + _R_NOT_YET_ANSWERED[422]["description"]
        ),
    },
}


def _refuse_answering_an_already_answered_key(
    draft: dict,
    answers_by_id: dict,
    timestamp: str,
    *,
    edit_at: str,
    identifiers: dict,
):
    """Refuse an ANSWER that would REPLACE a confirmed value. ``None`` to proceed.

    THE MIRROR OF :func:`_refuse_correcting_an_unanswered_key`, and the half that was
    missing. That one closes ``/edit`` against a question nobody has answered; this one
    closes ``/answers`` against a question somebody already has. The two routes divide
    the work \u2014 ``/answers`` answers OPEN questions, ``/edit`` corrects
    ALREADY-ANSWERED ones \u2014 and until now only one side of the division was enforced.

    THE DEFECT THIS CLOSES, measured over HTTP on a record created through
    ``POST /api/experiments``, with a stored ``series_id`` of ``race-a`` and ``race-b``
    submitted::

        POST /runs/{run_id}/answers {"series": <race-b>}
          -> 200
             invalidation.changed        false
             invalidation.rev            unmoved
             invalidation.reason         "No change \u2014 the submitted value was
                                          identical; nothing was invalidated."
             stored series_id AFTER      race-a

    The value was neither identical nor ever stored. That is the same sentence, and the
    same two false claims, that :func:`_answers_to_apply_shape`'s docstring already
    records for the ASSET key on the CORRECTION route \u2014 *"false twice over, because
    the value was neither identical nor ever stored"* \u2014 left live on the opposite
    route. It was measured on FIVE key/level combinations, not the one it was reported
    on: ``series``, ``qc`` and ``descriptor`` on ``/runs/{run_id}/answers``, ``series``
    on the record's ``/answers``, and a stored asset uri re-answered with a DIFFERENT
    sha256 on the record's ``/answers``.

    WHY THE ANSWER IS ALWAYS DISCARDED, structurally rather than by luck.
    :func:`~isaac_records.complete.apply_answers` iterates ``draft["pending"]`` and
    writes only inside a branch it entered from a pending entry. A closed question has no
    entry, so no branch is entered and no value is written \u2014 for every kind,
    including assets, whose materialised entry is removed from ``pending`` when it
    resolves. The route then reports ``changed=False``, and
    ``dependencies.build_invalidation`` cannot tell "the caller resubmitted the identical
    value" from "we dropped what the caller sent", so it says the first about both.

    **IT FIRES ONLY WHERE THE VALUES DIFFER, AND THAT IS NOT A SOFTENING \u2014 IT IS
    WHAT MAKES THE SENTENCE TRUE AGAIN.** An identical resubmission is a real,
    documented, load-bearing behaviour: three tests
    (``test_versioning::test_http_answers_noop_reentry_does_not_bump_rev``,
    ``test_dependency_invalidation::test_noop_resubmission_invalidates_nothing_and_does_not_bump_rev``,
    ``test_experiment_repository::test_an_identical_re_entry_through_the_api_still_succeeds``)
    pin that a client may repeat a request it is unsure landed and get ``200`` with an
    unmoved revision. A first draft of this refusal broke all three, which is how the
    requirement was found rather than assumed. For an identical resubmission the sentence
    "the submitted value was identical" is simply TRUE and nothing was lost; only a
    DIFFERING value is a discarded one.

    **EQUALITY IS ASKED OF THE TRUTH CORE, NOT RE-IMPLEMENTED HERE, and that is the
    load-bearing design choice.** ``apply_corrections`` already answers exactly this
    question for exactly these keys \u2014 its own comment reads *"Each branch guards on
    an EQUALITY check first: an identical re-confirm changes NOTHING (no overwrite, no
    fresh evidence, no wrapper-timestamp churn), so the authoritative draft signature
    stays byte-stable"* \u2014 and it knows things a route must not restate: that a
    descriptor is compared with its ``evidence`` excluded, that a qc verdict is compared
    as the ``(status, note)`` PAIR (the C1/I3 defects recorded in that function), and
    where each value physically lives. So the probe is
    ``apply_corrections(draft, one_key_shape) != draft``, over a pure deep-copying
    function that writes nothing and persists nothing. A hand-written comparison of five
    storage layouts is precisely the duplication that drifts, and it would have had to be
    got right in a file that must not know those layouts.

    THREE CONSEQUENCES OF PROBING WITH THE CORRECTION WRITER, all of them wanted:

    * ``answer_at`` IS PROVABLY ACTIONABLE rather than plausibly so. A key is refused
      only if ``apply_corrections`` would write it, which means it is ``series``,
      ``descriptor``, ``qc`` or a stored asset uri \u2014 so
      :func:`_has_correction_target` is satisfied, :func:`_correction_is_storable` is
      satisfied (the writer accepted the value), and
      :func:`_refuse_correcting_an_unanswered_key` cannot fire (the question is closed).
      ``/edit`` is therefore guaranteed to accept what this refusal redirects, which is
      the property that function's docstring says a refusal must have: *"a refusal that
      misdirects is worse than one that says nothing."*
    * A BARE ``descriptor_label`` FALLS OUT ON ITS OWN. ``apply_corrections`` gates the
      whole descriptor block on ``descriptor is not None``, so a label with no descriptor
      changes nothing and is never refused \u2014 matching both edit operations, which
      answer it ``422 unrecognized_field`` (measured over HTTP at both levels). No
      special case was needed and none is written; had one been, it would have named
      ``/edit`` for a key ``/edit`` rejects.
    * AN UNUSABLE VALUE IS NOT REFUSED HERE. ``apply_corrections`` declines a value it
      cannot store, so the probe reports no change and this function proceeds. That case
      keeps its existing behaviour and is deliberately NOT changed by this slice: it
      belongs to the route's unusable-value doctrine
      (:func:`_correction_is_storable` / ``invalid_field_value``), which is a different
      rule at a different layer, and adopting it on the answers path would also change
      what an unusable answer to an OPEN question does \u2014 where the returned
      ``pending`` list already tells the caller the answer did not land.

    ``edge`` IS OUT OF SCOPE for the reason the mirror gives: it corresponds to no
    blocker, so "closed" is not a state it can be in. It is excluded STRUCTURALLY, by
    consulting :data:`_CORRECTABLE_KEY_KINDS` rather than the writer's key set \u2014
    which matters, because the record operation's own response documentation promises
    that ``edge`` is answerable there even on a record that has runs.

    THE CLOSED CHECK COMES FIRST, AND NOT ONLY FOR SPEED. An OPEN question stores
    nothing, so ``apply_corrections`` would report a change for it too \u2014 probing
    without the state check would refuse the ordinary, correct use of this route. It also
    means a request that answers only open questions performs no probe at all, so the
    common path costs nothing.
    """
    pending = [e for e in (draft.get("pending") or []) if isinstance(e, dict)]
    open_kinds = {e.get("kind") for e in pending}
    open_asset_uris = {e.get("uri") for e in pending if e.get("kind") == "asset"}
    stored_uris = {
        a.get("uri") for a in (draft.get("assets") or []) if isinstance(a, dict)
    }
    offending = []
    for key, value in (answers_by_id or {}).items():
        if value in (None, ""):
            continue
        kind = _CORRECTABLE_KEY_KINDS.get(key)
        if kind is not None:
            if kind in open_kinds:
                continue
        elif key not in stored_uris or key in open_asset_uris:
            # Not a named answer key and not a stored asset uri -> nothing this refusal
            # has an opinion about. The `open_asset_uris` half is defence in depth, not
            # a live case: `apply_answers` removes an asset's pending entry when it
            # materialises it, so a uri cannot normally be both. If one were, the answer
            # WOULD apply and must not be refused.
            continue
        # The question is closed. Does this value differ from the confirmed one?
        # `edit_only=True` builds the shape `/edit` WOULD build: it narrows asset uris to
        # the stored ones and forwards `qc` unscreened, which is what makes the probe an
        # answer about this VALUE rather than about the answers path's own filtering.
        probe = _answers_to_apply_shape({key: value}, draft, timestamp, edit_only=True)
        if apply_corrections(draft, probe) != draft:
            offending.append(key)
    if not offending:
        return None
    content: dict = {
        "error": "already_answered",
        **identifiers,
        "keys": sorted(offending),
        "answer_at": edit_at,
    }
    content["message"] = (
        "Each of these is already answered, and the value submitted here differs from "
        "the confirmed one. This operation answers open questions only, so applying it "
        "would have discarded what you sent while reporting no change. Nothing was "
        "written and the stored value is unchanged. Correct it at the operation named "
        "in `answer_at` instead \u2014 the ids to substitute into it are in this same "
        "body. Resubmitting the value that is already stored is still accepted here."
    )
    return JSONResponse(status_code=422, content=content)


def _refuse_correcting_an_unanswered_key(
    draft: dict,
    answers_by_id: dict,
    *,
    answer_at: str | None,
    identifiers: dict,
):
    """Refuse a CORRECTION of a key that is still an open question. ``None`` to proceed.

    THE DEFECT THIS CLOSES, measured over MCP by an independent review before it was
    written. ``/edit`` admitted ``series``, ``descriptor`` and ``qc`` unconditionally,
    while ``apply_corrections`` deliberately never touches ``pending`` (its own
    docstring says so). So correcting a question nobody had answered returned::

        POST /edit {"series": [...]}   ->  200, changed_fields: ["series"]
        GET  /pending                  ->  "series" STILL OPEN

    The value was written into the draft, carrying a fresh ``user_confirmation``, and
    the question the scientist was looking at did not move. That is a ``200`` about a
    write that resolved nothing — the exact class the sibling refusals on this route
    exist to close, reachable one key over. Export stayed gated by ``pending``, so no
    invalid record could ship; what shipped was a false report.

    IT IS A TYPED REFUSAL RATHER THAN A DROPPED KEY, and that distinction is this
    route's own doctrine. Dropping the key would make :func:`_has_correction_target`
    answer ``False`` and produce ``unrecognized_field`` — "this application does not
    know that field" — when the field is recognised and only its STATE is wrong. That
    is the same mistake the ``qc`` screening comment in
    :func:`_answers_to_apply_shape` records having made once already: it sends a
    scientist looking for a misspelling that is not there.

    ASSETS AND ``edge`` ARE DELIBERATELY OUT OF SCOPE, each for its own reason. An
    unanswered asset is already dropped structurally on the ``edit_only`` path, so it
    never gets here. ``edge`` corresponds to no blocker, so "unanswered" is not a
    state it can be in.

    **BOTH CONDITIONS ARE REQUIRED, AND THE SECOND WAS FOUND BY A TEST GOING RED
    RATHER THAN BY THINKING ABOUT IT.** "Is the question open" alone is WRONG for a
    LEGACY RUN: a run created before ``_seed_for_new_run`` existed carries no
    ``pending`` key, so ``_apply_to_run`` materialises one from
    ``ws.run_questions`` — which derives it from the blank-draft template and
    therefore lists ``qc`` even for a run that already HOLDS a verdict. Refusing
    there would refuse a legitimate correction of a real stored value, and
    ``test_editing_a_legacy_run_does_not_erase_its_questions_either`` said so
    immediately.

    So a key is refused only when it is BOTH listed as open AND absent from the
    draft. That is structurally the same rule the asset path already applies
    (``asset_uris = stored_uris``): what makes a correction legitimate is that there
    is something stored to correct.

    ``answer_at`` IS A PARAMETER BECAUSE IT WAS A HARDCODED LITERAL AND THE LITERAL WAS
    WRONG AT ONE OF THE TWO CALL SITES. It read
    ``"POST /api/experiments/{experiment_id}/answers"`` — the RECORD's operation — and
    this function is also called from the RUN correction path, where every one of the
    four keys it can refuse is run-owned. Measured over HTTP on a record with one run,
    correcting its never-answered ``qc``::

        POST /runs/{run_id}/edit {"qc": {...}}   -> 422 not_yet_answered
                                                   answer_at: POST …/answers   (record)
        POST /answers            {"qc": {...}}   -> 409 belongs_to_a_run
                                                   answer_at: POST …/runs/{run_id}/answers

    So a client that did exactly what the first refusal told it to do was refused again,
    by a route that is *guaranteed* to refuse it — ``_refuse_run_level_on_the_record``
    exists precisely to refuse a run-owned key on a record that has runs — and had to
    follow a SECOND redirect to reach the operation the first refusal should have named.
    A refusal that misdirects is worse than one that says nothing: it spends the caller's
    retry and reads as authoritative while doing it.

    THE RECORD CALL SITE STILL PASSES THE RECORD'S OPERATION, and that is a conditional
    fact rather than a constant one. Every key in :data:`_CORRECTABLE_KEY_KINDS` is also
    a key in :data:`_RUN_LEVEL_ANSWER_BLOCK`, and on the record path
    ``_refuse_run_level_on_the_record`` runs FIRST — so this refusal is reachable there
    only on a record with no runs, which is exactly the record whose own ``/answers``
    accepts the key. Measured in both directions: with a run, the record path answers
    ``409 belongs_to_a_run`` and never reaches here; with no runs it answers this
    ``422``. The record call site therefore passes ``None`` when ``exp.runs`` is
    non-empty rather than relying on that ordering — the guarantee is a property of two
    functions and of ``workspace.RUN_LEVEL_BLOCKS``, and if any of the three changes the
    honest outcome is *no* ``answer_at``, not a stale one.

    ``None`` IS THEREFORE A SUPPORTED VALUE AND OMITS THE KEY. Emitting an operation the
    application would refuse is the defect above; emitting nothing, and saying in
    ``message`` that nothing can resolve it here, is the honest alternative. The key is
    omitted rather than set to ``null`` so a client cannot mistake "no route" for a route
    whose name failed to render.

    ``identifiers`` carries the concrete ids — ``experiment_id``, plus ``run_id`` on the
    run path — beside the template, which is the convention ``belongs_to_a_run`` and every
    other operation pointer in this module already follows. A caller substitutes them; the
    refusal never ships a half-interpolated URL.
    """
    open_kinds = {
        entry.get("kind")
        for entry in (draft.get("pending") or [])
        if isinstance(entry, dict)
    }
    offending = sorted(
        key
        for key, value in (answers_by_id or {}).items()
        if value not in (None, "")
        and _CORRECTABLE_KEY_KINDS.get(key) in open_kinds
        and not draft.get(_CORRECTABLE_KEY_STORAGE.get(key, key))
    )
    if not offending:
        return None
    content: dict = {"error": "not_yet_answered", **identifiers, "keys": offending}
    if answer_at is not None:
        content["answer_at"] = answer_at
    content["message"] = (
        "Each of these is still an open question, so there is no confirmed value to "
        "correct. Correcting one would store the value and leave the question open, "
        "which would report a change that resolved nothing. "
        + (
            "Answer it at the operation named in `answer_at` instead — the ids to "
            "substitute into it are in this same body. Nothing was written."
            if answer_at is not None
            else "No operation on this record can answer it: the record has runs, so a "
            "spectrum, a QC verdict, a descriptor and an asset hash belong to the run "
            "that measured them. No `answer_at` is given rather than one that would "
            "refuse the request. Nothing was written."
        )
    )
    return JSONResponse(status_code=422, content=content)


def _has_correction_target(apply_shape: dict) -> bool:
    """True iff ``apply_shape`` names at least one recognized correction field.

    An asset sha256 (keyed by a known uri), a series/descriptor/edge/qc value. A bare
    ``descriptor_label`` (or only ``timestamp``/``asset_sha256:{}``) is NOT an
    actionable correction — an edit body that reduces to nothing recognized is
    rejected (422) rather than silently no-op'd, so an unknown field is never
    quietly swallowed.
    """
    return bool(apply_shape.get("asset_sha256")) or any(
        k in apply_shape for k in ("series", "descriptor", "edge", "qc")
    )


def _fields_the_shape_carries(apply_shape: dict, submitted_fields: list[str]) -> list[str]:
    """The submitted keys the apply-shape ACTUALLY carries, in submission order.

    NOT ``submitted_fields``, which is every non-blank REQUEST-BODY key regardless of
    whether the core ever saw it. Measured on the old code, and worse than silence:

      ``{<a stored asset uri>: <a valid sha>, "totally_made_up_field": "invented"}``
      answered ``200`` with ``changed_fields`` naming BOTH keys and ``reason`` reading
      "Updated 2 field(s); no downstream steps reopened", while
      ``totally_made_up_field`` was dropped by :func:`_answers_to_apply_shape` and appears
      nowhere in the stored draft.

      ``qc`` did the same and is the more insidious one, because it is a REAL field:
      :func:`~isaac_records.complete.apply_corrections` handles it, but the apply-shape
      does not produce it, so a ``qc`` key was reported as an updated field while
      ``draft["qc"]["status"]`` never moved.

    A field the record never received must not be reported as updated. The count in
    ``reason`` is derived from this list too, so both the list and the sentence become
    claims about what was actually forwarded.

    This is narrower than "what was written". A key the shape carries can still be
    declined further down (an ``edge`` correction on a draft with no implicit ``edge``
    entry writes nothing), and this function does not detect that — it removes the claims
    that are provably false, and does not pretend to per-field write confirmation the
    core does not report.
    """
    carried = set(apply_shape.get("asset_sha256") or {})
    carried |= {k for k in apply_shape if k not in ("timestamp", "asset_sha256")}
    return [k for k in submitted_fields if k in carried]


#: Where in a draft each shaped-answer key's VALUE actually lives.
#:
#: Read against :func:`_answers_to_apply_shape`, which is the only producer of these
#: keys, and pinned by ``test_answers_report_only_what_landed.py`` so a key added
#: there without a slot here fails loudly instead of silently reverting to the weaker
#: claim this table exists to replace. Asset keys are absent deliberately: an asset is
#: keyed by its URI, so it has no fixed name to list — it is handled by
#: :func:`_asset_entry` below.
_ANSWER_KEY_VALUE_SLOT: dict[str, str] = {
    "series": "series",
    "descriptor": "descriptors_outputs",
    # `descriptor_label` is written only by the branch that writes `descriptors_outputs`
    # (``complete.apply_answers`` / ``apply_corrections`` build the whole block), so a
    # label whose descriptor was declined lands nowhere and shares the slot.
    "descriptor_label": "descriptors_outputs",
    "qc": "qc",
    "edge": "implicit",
}


def _asset_entry(draft: dict, uri: str) -> dict | None:
    """The stored asset with this URI, or ``None``. Compared before/after a write."""
    for asset in draft.get("assets") or []:
        if isinstance(asset, dict) and asset.get("uri") == uri:
            return asset
    return None


def _open_blockers(draft: dict) -> tuple[frozenset[str], frozenset[str]]:
    """``(open blocker kinds, open asset URIs)`` for one draft."""
    entries = [e for e in (draft.get("pending") or []) if isinstance(e, dict)]
    return (
        frozenset(e.get("kind") for e in entries),
        frozenset(e.get("uri") for e in entries if e.get("kind") == "asset"),
    )


def _fields_the_write_landed(
    apply_shape: dict, submitted_fields: list[str], before: dict, after: dict
) -> list[str]:
    """The carried keys whose write ACTUALLY LANDED, in submission order.

    THE DEFECT THIS CLOSES, measured over HTTP by an independent review, on a LEGACY
    run — a run created before ``_seed_for_new_run`` existed, so its draft has no
    ``pending`` key::

        POST .../runs/{run_id}/answers  {"series": "not-a-list"}
          -> 200
             invalidation.changed        true
             invalidation.changed_fields ["series"]
             invalidation.reason         "Updated 1 field(s); no downstream steps
                                          reopened."
             stored series AFTER         None
             `series` STILL an open question

    The same request against a SEEDED run correctly reported ``changed: false``. The
    two halves came from different places and only one of them was about the write:
    ``changed`` is ``save_versioned()``'s answer, which is true here because
    ``_apply_to_run`` MATERIALISES a legacy run's derived questions into the document
    before writing — a real change to the document — while ``changed_fields`` was
    :func:`_fields_the_shape_carries`, derived from the SUBMITTED shape. So a field
    that was never written was named as updated, and the sentence counted it.

    **THIS IS THE MIRROR OF THE ``already_answered`` DEFECT THIS BRANCH FIXED, WITH
    THE POLARITY REVERSED**, on exactly the runs the branch's legacy handling was
    written for: that one reported *"the submitted value was identical"* about a value
    that had changed; this one reported *"Updated 1 field(s)"* about a value that had
    not been stored at all.

    **THE LEGITIMATE HALF IS PRESERVED DELIBERATELY.** Materialising a legacy run's
    template IS a change to the document, the revision SHOULD move, and ``changed``
    stays true — that is not the defect and reverting it would re-open the 200 that
    destroyed a run's questions. What must not happen is NAMING a field that was not
    written, and that is all this narrows.

    TWO TESTS PER FIELD, BECAUSE ONE IS NOT ENOUGH FOR EITHER WRITER:

    * the VALUE SLOT moved — the rule that fits ``apply_corrections``, which never
      touches ``pending`` and whose whole job is to overwrite a stored value; and
    * the field's own BLOCKER was resolved — the rule that fits ``apply_answers``,
      which removes a ``pending`` entry exactly when it applied that entry's value.
      It catches the one case the slot comparison cannot: a legacy run whose draft
      already holds a ``qc`` verdict beside an open ``qc`` blocker (the state
      ``_apply_to_run`` materialises), answered with the value already stored. The
      value does not move; the question is genuinely closed.

    Evidence-only movement is NOT counted, and that is a decision rather than an
    omission. ``block_evidence`` is shared between fields — ``series`` and ``qc`` both
    append to it — so treating it as a per-field signal would report ``qc`` as updated
    because ``series`` was. A field whose value did not move and whose question stayed
    open was not updated, whatever else the write touched; ``changed`` reports that
    the document moved, which is a different claim and still true.

    NARROWER THAN :func:`_fields_the_shape_carries` AND LAYERED ON TOP OF IT, not a
    replacement: that function removes keys the core never received, this one removes
    keys the core received and declined.
    """
    carried = _fields_the_shape_carries(apply_shape, submitted_fields)
    asset_uris = set(apply_shape.get("asset_sha256") or {})
    kinds_before, uris_before = _open_blockers(before)
    kinds_after, uris_after = _open_blockers(after)
    landed: list[str] = []
    for key in carried:
        if key in asset_uris:
            if _asset_entry(before, key) != _asset_entry(after, key) or (
                key in uris_before and key not in uris_after
            ):
                landed.append(key)
            continue
        slot = _ANSWER_KEY_VALUE_SLOT.get(key)
        kind = _CORRECTABLE_KEY_KINDS.get(key)
        if slot is None and kind is None:
            # A key `_answers_to_apply_shape` produces that this table does not know.
            # Keep the older, weaker claim rather than dropping the field silently —
            # under-reporting an update is its own false statement. The pinning test
            # is what stops this branch from ever being the live path.
            landed.append(key)
            continue
        if slot is not None and before.get(slot) != after.get(slot):
            landed.append(key)
            continue
        if kind is not None and kind in kinds_before and kind not in kinds_after:
            landed.append(key)
    return landed


@router.post(
    "/experiments/{experiment_id}/edit",
    tags=[TAG_DRAFTS],
    summary="Correct an Already-Answered Field",
    description=(
        "Overwrites the current value of a field that has already been answered, "
        "recording a fresh user confirmation, and returns the same refreshed "
        "bundle as the answers operation.\n\n"
        "Requires `confirmed_by_user: true` and the record's current `ETag` in "
        "`If-Match`. A body that names no recognised editable field is rejected "
        "with `422` rather than silently doing nothing, and so is a recognised "
        "field carrying a value the record cannot store — the refusal happens "
        "before any mutation, so the stored value is unchanged. It never reopens "
        "or creates a blocking question.\n\n"
        "Only a field that is already answered can be corrected here. An asset "
        "whose hash is still an open question is answered through the answers "
        "operation, not this one."
        "\n\n" + _BOUNDED_PENDING_PARAGRAPH
    ),
    response_description=(
        "The refreshed blocking questions, status, revision metadata, workflow, "
        "and the downstream invalidation, with the new `ETag`."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        **_R_PRECONDITION,
        # DECLARED, because the generated 422 said only "Validation Error" while this
        # operation refuses four DOMAIN conditions under that status, each with a body
        # the framework's schema does not describe. `_R_CORRECTION_REFUSED` carries
        # them, and it is SHARED with the run-level correction operation because that
        # one refuses the identical four — see the constant for why one declaration is
        # safer than two, and for the `not_yet_answered` one that was missing from the
        # enumeration here while this route performed it.
        **_R_CORRECTION_REFUSED,
        **_R_BELONGS_TO_A_RUN,
    },
)
def post_edit(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"confirmed_by_user\": true, \"answers\": {<key>: <value>}}`, where "
            "each key names a field already present in the draft. Omitting "
            "`confirmed_by_user: true`, or naming no recognised editable field, is "
            "rejected with `422`."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The record's current `ETag`, exactly as a read operation "
            "returned it."
        ),
    ),
):
    # Mirrors post_answers EXACTLY: existence pre-check OUTSIDE the lock so a bogus
    # id never pins a permanent entry in the never-evicting per-record lock map.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    # The per-record lock serialises load->precondition->mutate->save; the record is
    # loaded FRESH inside the lock so two writers holding the same token cannot both
    # succeed (compare-and-swap).
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        if body.get("confirmed_by_user") is not True:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "confirmation_required",
                    "message": "confirmed_by_user must be true to correct a field.",
                },
            )
        err = _check_if_match(if_match, exp)
        if err is not None:
            return err
        # Capture the PRE-mutation workflow so the invalidation reports the reopen
        # DELTA (which completed steps, if any, regressed) after the correction.
        pre_steps = _workflow_for(exp)["ordered_steps"]
        submitted_fields = [
            k for k, v in (body.get("answers") or {}).items() if v not in (None, "")
        ]
        timestamp = _now_iso()
        # `edit_only`: a CORRECTION can only overwrite an asset that exists. A pending
        # asset uri is not an editable field here (see `_answers_to_apply_shape`), so it
        # falls through to the "no recognised editable field" refusal below instead of
        # being absorbed with a 200 that reports a write which could not happen.
        apply_shape = _answers_to_apply_shape(
            body.get("answers") or {}, exp.draft, timestamp, edit_only=True
        )
        # WHAT THE MAPPER DROPPED. This route keeps its ride-along tolerance — a body
        # naming one editable field plus one unknown one is a `200` reporting only what
        # landed, pinned by an argued test — but a `changed=False` on such a body may no
        # longer be explained as "the submitted value was identical", because a reader
        # would apply that to the key that vanished. `edit_only=True` matches the shape
        # this route actually built.
        dropped = _dropped_answer_keys(
            body.get("answers") or {}, exp.draft, edit_only=True
        )
        refusal = _refuse_run_level_on_the_record(exp, apply_shape)
        if refusal is not None:
            return refusal
        # BEFORE the correction-target check, because the two refusals say different
        # things and this one is the more specific: "still open" rather than "not
        # recognised". The order is what keeps a scientist from being sent to look
        # for a misspelling in a field name that is spelled correctly.
        refusal = _refuse_correcting_an_unanswered_key(
            exp.draft,
            body.get("answers") or {},
            # THE RECORD'S OWN `/answers` ONLY WHEN IT CAN ACTUALLY TAKE THE KEY. Every
            # key this refusal can name is run-owned, so on a record that has runs the
            # record-level operation would answer `409 belongs_to_a_run` — and the
            # refusal above has already returned that, which is why `None` here is a
            # branch this call cannot currently reach (measured: with a run the record
            # path answers 409 and never arrives). It is passed anyway rather than
            # assumed away: the unreachability rests on the ordering of two refusals
            # and on `workspace.RUN_LEVEL_BLOCKS`, and if any of that moves, no
            # `answer_at` is the truthful output and a stale one is not.
            answer_at=None if exp.runs else _ANSWERS_OPERATION_RECORD,
            identifiers={"experiment_id": exp.id},
        )
        if refusal is not None:
            return refusal
        if not _has_correction_target(apply_shape):
            # No recognized field to correct — never invent one.
            return JSONResponse(
                status_code=422,
                content={
                    "error": "unrecognized_field",
                    "message": "No editable field was recognized in the request.",
                },
            )
        # THE SAME `edge` SCREEN THE ANSWERING PATH APPLIES, and this route needed it for
        # the same reason. `edge` is in `_has_correction_target`'s key set, so a bare
        # `{"edge": ...}` gets past that check; it is absent from `_CORRECTABLE_KEY_KINDS`
        # (it corresponds to no blocker, so "unanswered" is not a state it can be in), so
        # `_refuse_correcting_an_unanswered_key` does not see it either. Between the two
        # it reached `apply_corrections`, which writes only into an `implicit[]` entry
        # that exists — and answered 200 having stored nothing.
        refusal = _refuse_edge_with_nothing_to_confirm(
            exp.draft, apply_shape, {"experiment_id": exp.id}
        )
        if refusal is not None:
            return refusal
        # A STRUCTURED CORRECTION OF THE WRONG TYPE IS REFUSED HERE, not absorbed.
        #
        # `apply_corrections` now REFUSES to apply a malformed `series` or `descriptor`
        # (see `complete.py`), which is what stops the two defects measured on the
        # unguarded code: a 500 out of the truth core for `5` / `"nope"` / `[1, 2]` / a
        # 1 MB string, and — worse — a 200 for `{}` that stored a dict where the schema
        # requires a list and DESTROYED an already-confirmed series.
        #
        # But refusing to apply it would leave this route answering 200 having changed
        # nothing, which its own description forbids in the sentence directly above:
        # a body that names no recognised editable field "is rejected with 422 rather
        # than silently doing nothing". A body that names one and gives it an
        # unusable value is the same case, so it gets the same typed refusal.
        #
        # NOT extended to `POST /answers`, deliberately. There, a value that cannot be
        # applied leaves the blocker OPEN, so the response already tells the caller the
        # question was not answered — and that behaviour is pinned by
        # `test_answers_wrong_type.py` and by a browser spec. `/edit` has no pending
        # blocker to leave open, so silence there is genuinely silent.
        wrong_typed = [
            key
            for key, value in apply_shape.items()
            if key not in ("timestamp", "asset_sha256")
            and not _correction_is_storable(key, value)
        ] + [
            uri
            for uri, sha in (apply_shape.get("asset_sha256") or {}).items()
            if not _correction_is_storable(uri, sha)
        ]
        if wrong_typed:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "invalid_field_value",
                    "key": wrong_typed[0],
                    "keys": wrong_typed,
                    # NAMES NO CAUSE, and the two type-specific clauses that used to be
                    # here were REMOVED rather than extended. They read "`series` must be
                    # a list of objects and `descriptor` must be an object" — measured
                    # verbatim on a body whose only offending key was an ASSET URI, and
                    # likewise for `descriptor_label`. The keys the refusal covers were
                    # widened without the sentence being touched, so its honesty depended
                    # on the browser client suppressing the server's own misstatement:
                    # every curl, OpenAPI reader and Assistant consumer saw the false
                    # text. `key`/`keys` already say WHICH field was refused; nothing here
                    # is entitled to say why.
                    "message": (
                        "This correction is not a shape the record can store, so nothing "
                        "was written. The stored value is unchanged."
                    ),
                },
            )
        # OVERWRITE the current value(s) for the recognized keys, recording a fresh
        # user_confirmation. apply_corrections never touches pending and never
        # invents a value (a malformed sha256 / off-enum qc leaves the value as-is).
        draft_before = exp.draft  # `apply_corrections` deep-copies; this stays pre-write
        exp.draft = apply_corrections(exp.draft, apply_shape)
        exp.answer_log.append({"edited": apply_shape, "at": timestamp})
        changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another replica won the race; this change was not applied
        if not changed:
            exp.answer_log.pop()  # byte-stable no-op: discard the speculative log append
        # WHAT LANDED, NOT WHAT WAS SUBMITTED. `_fields_the_shape_carries` removes keys
        # the core never received; `_fields_the_write_landed` additionally removes keys
        # it received and DECLINED — a wrong-typed `series` reported "Updated 1
        # field(s)" while the stored value was `None`. See that function for the
        # measurement. `Updated 0 field(s)` is now reachable with `changed: true`, on a
        # write whose only effect was materialising a legacy run's derived questions;
        # that sentence is literally true and is left alone rather than replaced with
        # one that would have to guess WHY the document moved.
        changed_fields = (
            _fields_the_write_landed(apply_shape, submitted_fields, draft_before, exp.draft)
            if changed
            else []
        )
        invalidation = dependencies.build_invalidation(
            changed=changed,
            changed_fields=changed_fields,
            pre_steps=pre_steps,
            post_exp=exp,
            # THE CALLER'S ANSWER TO "DID YOU COMPARE?" — see
            # `_resubmission_was_identical` for why a fully storable non-empty shape
            # plus `changed=False` IS an identical resubmission, and why an empty one
            # is not. `build_invalidation` names no cause without it.
            #
            # `and not dropped` IS THE OTHER HALF, and it is the half that closes the
            # ride-along case. A body carrying one recognised key beside one unrecognised
            # one still has the unrecognised one dropped in silence; what it must not
            # also get is a sentence saying the submitted value was already stored, which
            # a reader would apply to the key that vanished. When anything was dropped
            # this route claims nothing.
            identical=_resubmission_was_identical(apply_shape) and not dropped,
        )
        # `exp.pending()`, NOT `exp.draft` — the SAME correction `GET /pending` needed.
        # An independent review measured the consequence of missing these two: after a
        # run existed, this response came back `pending: []` while the detail response
        # said three questions remained, and `GuidedCompletion` renders "All blockers
        # resolved" on an empty list. The screen a scientist answers questions on told
        # them they were finished, about a record that could not export.
        result = _mutation_pending_response(exp, experiment_id, unit_run_id=None)
        result["status"] = exp.status()
        result.update(vc.version_fields(exp))
        result["workflow"] = _workflow_for(exp)
        result["invalidation"] = invalidation
        response.headers["ETag"] = exp.etag()
        return result


# --- 7c. runs ------------------------------------------------------------------
#
# The Run DOMAIN MODEL already exists in `workspace` (contract §1 D1: one Run is one
# official ISAAC record). This section only EXPOSES it. It adds no storage: a run
# lives inside its experiment's state document, so every write here goes through the
# same `record_lock` -> load fresh -> precondition -> mutate -> `save_versioned`
# sequence `post_edit` uses, and therefore inherits the durable compare-and-swap in
# `experiment_repository.Q_UPSERT_EXPERIMENT` without naming it.
#
# TWO DIFFERENT VALIDATORS GUARD TWO DIFFERENT THINGS, and confusing them is the
# mistake this comment exists to prevent. Creating a run REWRITES THE EXPERIMENT
# document (the run list is part of it), so `POST .../runs` takes the EXPERIMENT's
# `If-Match`. Editing one run's own draft is addressed to that run, so
# `PATCH .../runs/{run_id}` takes the RUN's `If-Match` — `Run.version_token()`,
# which `workspace` minted for exactly this purpose and which no route consumed
# until now.


#: The path parameter naming a run. One description, so the wording cannot drift.
RunId = Annotated[
    str,
    Path(
        description=(
            "The id of a run of this experiment, as returned by "
            "`GET /api/experiments/{experiment_id}/runs`."
        )
    ),
]

# `_R_RUN_NOT_FOUND` MOVED UP, next to `_R_EXPERIMENT_NOT_FOUND`. It is read by a
# route decorator that executes far earlier in this module than this line does —
# `GET /experiments/{id}/pending`, which grew a `run_id` filter and so grew that
# 404 — and a decorator argument is evaluated at import time, so defining it here
# would have been a ~~ImportError waiting for the first caller who needed it
# earlier~~ **`NameError` raised while importing this module**, before any route was
# registered and before any caller existed. Naming the wrong exception mattered
# enough to correct: an `ImportError` reads as a dependency problem a reader would
# go looking for in another file.

_R_RUN_EXPORTED: dict = {
    409: {
        "description": (
            "An official ISAAC record for this run already exists, so it was not "
            "removed and nothing was written. `error` is `run_exported`. "
            "**`record_stem` names the artifact** — read that one, not `record_id`. "
            "`record_id` reports the run's persisted record id and is `null` on the "
            "arm where a record and/or its evidence sidecar are on disk but no "
            "`record_id` was persisted; `record_stem` is the run's own id there. "
            "Either file alone is enough to refuse, so a refusal does not imply "
            "both exist. Only the removal operation can answer this."
        )
    },
}

#: The three states a run's view of one inherited experiment-level address can be in.
RUN_INHERITED = "inherited"
RUN_OVERRIDDEN = "overridden"
RUN_ABSENT = "absent"


class _RunPrecondition:
    """A run, presented to the ``If-Match`` helpers in the shape they already read.

    `_check_if_match`, `_precondition_required`, `_malformed_if_match` and
    `_stale_write` read exactly four things — ``.id``, ``.rev``, ``.etag()`` and
    ``.version_token()`` — plus, now, an optional ``precondition_identity``. A run
    supplies all five, so the run's precondition is classified by the SAME code that
    classifies an experiment's, rather than by a second implementation that would be
    free to drift on the day one of the two is fixed.

    ``precondition_identity`` carries BOTH ids. A refused run write names the run it
    was addressed to and the experiment it belongs to; filing the run id under
    ``experiment_id`` would be a false statement in the one body a client reads when
    its write is refused.
    """

    def __init__(self, run: "ws.Run", experiment_id: str) -> None:
        self._run = run
        self.id = run.id
        self.precondition_identity = {"experiment_id": experiment_id, "run_id": run.id}

    @property
    def rev(self) -> int:
        return self._run.rev

    def version_token(self) -> str:
        return self._run.version_token()

    def etag(self) -> str:
        return f'"{self._run.version_token()}"'


def _run_not_found(experiment_id: str, run_id: str) -> JSONResponse:
    """A run this experiment does not have. Distinct from `_not_found`.

    The two 404s are deliberately different bodies: ``experiment_not_found`` means
    the workspace has no such record, ``run_not_found`` means the record exists and
    was read successfully and simply holds no run under that id. Collapsing them
    would tell a client to go looking in the wrong place.
    """
    return JSONResponse(
        status_code=404,
        content={
            "error": "run_not_found",
            "experiment_id": experiment_id,
            "id": run_id,
        },
    )


def _run_published_stem(exp: "ws.Experiment", run: "ws.Run") -> str | None:
    """The record stem this run keeps claimed, or ``None`` if it keeps none.

    THE GUARD ASKS ABOUT DISK, NOT ONLY ABOUT STATE, AND THE DIFFERENCE IS A
    DELETED OFFICIAL RECORD.

    The first version of this guard was `run.record_id is not None`, on the stated
    reasoning that "a run whose `record_id` is set has an official record and an
    evidence sidecar on disk". That direction is true and is not the one the safety
    argument needs. What it needs is the CONVERSE — a run whose `record_id` is not
    set has no pair on disk — and this codebase names the state where the converse
    is false, twice:

      * `post_export`'s 412 branch: "EVERY unit's artifact PAIR was already written
        to disk and the state was not";
      * `_save_versioned`: "`post_export` writes the official record and its
        evidence sidecar BEFORE calling this, and those two files remain on disk".

    `_write_record` sets `record_id` in memory and writes both files; one
    `_save_versioned` then persists. A lost durable compare-and-swap, or a raise
    between two units' writes, leaves the pair on disk with `record_id`
    unpersisted. Independent review reproduced exactly that shape and drove the
    real routes: the removal returned 200, the next export pruned the orphan, and
    a published record AND its evidence sidecar were deleted.

    `ExportUnit.materialised()` already encodes the correct three-part test; this
    is the same question asked of a run that may not be a current unit any more.
    Two `stat()` calls under a lock this route already holds.

    Returns the STEM rather than a bool so the refusal can name the artifact even
    on the arm where `record_id` is unset — the arm where a message built from
    `record_id` would say `null`.
    """
    record_id = run.record_id
    if isinstance(record_id, str) and ws.is_record_id(record_id):
        return record_id
    # No persisted `record_id`. A pair may still be on disk under the RUN's own id:
    # that is the stem `_write_record` uses for a run unit, and the stem the prune
    # would delete.
    #
    # THE SHAPE IS CHECKED BEFORE THE ID BECOMES A PATH, for the reason
    # `ExportUnit.record_path()` checks it (`workspace.py`): this is a place where
    # document content would otherwise become a filesystem path, and `RunId` is a
    # bare `str` path parameter with no pattern. Reaching it needs a crafted
    # persisted document and the impact is bounded to two read-only `stat()` calls
    # plus an echoed stem — so this is defence in depth, not a live hole. It is here
    # because the sibling function guards the identical step and an asymmetry between
    # them is the kind of thing that stops being harmless after a later change.
    if not ws.is_record_id(run.id):
        return None
    records_dir = exp.records_dir
    if (records_dir / f"{run.id}.json").exists() or (
        records_dir / f"{run.id}.evidence.json"
    ).exists():
        return run.id
    return None


def _run_exported(experiment_id: str, run: "ws.Run", *, stem: str | None = None) -> JSONResponse:
    """A run that has produced an official record, refused for removal.

    THIS IS THE HISTORY GUARD, and it is stated here rather than only in the
    operation's prose because it is the reason the operation is narrower than the
    button a scientist sees. A run that keeps an official record and an evidence
    sidecar claimed — whether by a persisted ``record_id`` or by a pair sitting on
    disk under its own id; see :func:`_run_published_stem` for why both are asked —
    holds a pair that is IMMUTABLE, because nothing in this application rewrites
    one. Removing the run would leave the pair claimed by
    no current unit, and the export prune deletes exactly that: a stem no current
    unit claims, protected only if a surviving record happens to link to it. So the
    removal that looks harmless here would become a DELETION of a published record
    on the next export of this experiment, at a distance, with no confirmation.

    Every run that has appeared in a submitted revision is such a run — a
    submission materialises every unit before it records anything — so refusing
    here is also what keeps a submitted record out of reach of this operation. The
    revision rows and the submission rows are append-only and survive regardless;
    this refusal is about the FILE.

    409 rather than 422: the request is well formed and the state of the record is
    what makes it impossible, which is what this API means by 409 everywhere else.
    """
    return JSONResponse(
        status_code=409,
        content={
            "error": "run_exported",
            "experiment_id": experiment_id,
            "id": run.id,
            # The STEM that is claimed, which on the disk-only arm is the run's
            # own id rather than a persisted `record_id`. `record_id` is reported
            # separately and honestly, including when it is null.
            "record_id": run.record_id,
            "record_stem": stem if stem is not None else run.record_id,
            "message": (
                "An official ISAAC record for this run already exists, so it "
                "cannot be removed. At least one published artifact is present — "
                "the record, its evidence sidecar, or both; either alone is "
                "enough. Published artifacts are never rewritten by this "
                "application, and the run is what keeps them claimed. Nothing "
                "was written."
            ),
        },
    )


def _resolution_state(resolution: "ws.Resolution") -> str:
    """Which of the three states a resolved inherited address is in, for a client.

    ``overridden`` whenever this run recorded an override — INCLUDING an override
    whose payload is ``None``, because a run that deliberately displaced an
    inherited value has not merely failed to receive one, and reporting that as
    ``absent`` would erase an audited act.

    ``absent`` when nothing is overridden and the experiment carries nothing at the
    address. That is reachable through :func:`workspace.resolve_inherited`'s key set,
    which is the union of the experiment's experiment-level addresses and the run's
    override addresses — a stored override at an address the experiment no longer
    carries resolves with ``inherited_payload=None``.
    """
    if resolution.provenance == ws.PROVENANCE_OVERRIDDEN:
        return RUN_OVERRIDDEN
    return RUN_INHERITED if resolution.payload is not None else RUN_ABSENT


def _blocker_message(entry: dict) -> str:
    """A human-readable line for ONE blocker. DERIVED, never invented.

    ``serialize.pending_to_list`` already returns the blocker's own
    ``question`` — the text the deterministic extractor wrote when it recorded
    that the value was missing. This picks the first of that blocker's own
    strings that actually says something and hands it back verbatim; it composes
    no new finding text, and it certainly states nothing about the science.

    The last branch is a DISCLOSURE OF ABSENCE, not a finding: a persisted
    blocker carrying no question, no ``about`` and no ``kind`` has no text to
    show, and saying so is the honest alternative to returning an empty string
    that a caller would render as a blank row. The ``message`` key is guaranteed
    to be present and non-empty on every element because a client renders a list
    of them and cannot be asked to invent the missing one itself.
    """
    for key in ("question", "about", "kind"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "A blocking question is open on this run, and it records no text."


def _run_view(exp: Experiment, run: "ws.Run") -> dict:
    """One run, as this API presents it.

    ``fields`` is the run's OWN draft field map — the run-level content it carries
    itself. Inherited experiment-level content is NOT merged into it, because
    contract §2 D2 makes inheritance a read-time resolution and never a copy; it is
    reported separately under ``inherited`` so a reader can see which is which.

    ``inherited`` is computed on read by :func:`workspace.resolve_inherited` and is
    never stored. Every payload it returns is already a deep copy, so nothing here
    can be written back through the response.

    ``overridable`` IS THE SERVER'S OWN ANSWER TO "MAY THIS RUN OVERRIDE HERE?", and
    it exists because the client had no way to ask. ``resolve_inherited``'s key set
    is every address ``field_level``/``block_level`` calls experiment-level — a
    segment-aware PREFIX test. :data:`EXPERIMENT_OVERRIDABLE_ADDRESSES` applies that
    test AND a second gate (membership in ``EXTRACTOR_FIELD_MAP`` for a ``field:``).
    The two sets are therefore NOT equal: ``field:system.domain`` passes the first and
    fails the second, and the committed seed draft carries it. So the panel rendered a
    row whose Override control could only ever return ``422 not_overridable`` — a
    control offered to a scientist with exactly one possible outcome, which is the
    defect.

    THE FIX IS A SERVER ANSWER, NOT A CLIENT CLASSIFIER, and that is the whole point.
    The alternative was transcribing the admissible-address set into the frontend
    bundle, which would be a second copy of a classification the client must not own —
    free to drift from this one silently. This flag is read from the SAME frozenset
    :func:`_override_address` gates on, so the answer the client renders and the answer
    the route enforces cannot disagree: they are one expression.

    IT IS A DISCLOSURE, NOT A GATE. Nothing here is a permission check — the route
    still refuses a direct request at a non-overridable address exactly as before, and
    a client that ignores this flag gets the same typed 422 it always did. Hiding an
    impossible control is a truthfulness fix on the READ side; the enforcement was
    never on this side and has not moved.
    """
    draft = run.draft if isinstance(run.draft, dict) else {}
    fields = draft.get("fields")
    return {
        "id": run.id,
        "experiment_id": run.experiment_id,
        "label": run.label,
        "ordinal": run.ordinal,
        "created_utc": run.created_utc,
        "updated_utc": run.updated_utc,
        "rev": run.rev,
        "version": run.version_token(),
        "record_id": run.record_id,
        "fields": copy.deepcopy(fields) if isinstance(fields, dict) else {},
        "inherited": {
            address: {
                "state": _resolution_state(resolution),
                "payload": resolution.payload,
                "inherited_payload": resolution.inherited_payload,
                "displaced_payload": resolution.displaced_payload,
                "overridable": address in EXPERIMENT_OVERRIDABLE_ADDRESSES,
            }
            for address, resolution in exp.resolve_run(run).items()
        },
    }


def _clean_label(
    raw: object, *, blank_is_a_choice: bool = True
) -> tuple[str | None, JSONResponse | None]:
    """``(label, None)`` or ``(None, <422>)``. A blank label is NOT a label.

    Absent or blank yields ``None``, which is how the caller says "you choose" —
    ``workspace.new_run`` then assigns ``Run <ordinal>``. A non-string is refused
    rather than coerced: ``str(5)`` would manufacture the label ``"5"`` out of a
    request that named none, which is the same guessing ``workspace._as_str``
    refuses on the read path.

    ``blank_is_a_choice`` IS THE DIFFERENCE BETWEEN CREATE AND EDIT, and it exists
    because collapsing them produced a measured silent no-op. On CREATE, blank
    genuinely means "server, you choose", and ``Run <ordinal>`` is a real answer.
    On EDIT there is nothing to choose: a rename to ``"   "`` used to return 200
    having renamed nothing and having said nothing, which is exactly the silent
    ignoring the edit route's own contract says never happens. Callers that edit
    pass ``blank_is_a_choice=False`` and get the same typed ``invalid_label``
    refusal a non-string already gets.
    """
    if raw is None:
        return None, None
    if not isinstance(raw, str):
        return None, JSONResponse(
            status_code=422,
            content={
                "error": "invalid_label",
                "message": "label must be a string, or omitted so the server assigns one.",
            },
        )
    # A LABEL GOES THROUGH THE SAME SERIALIZER AS A FIELD VALUE, so it needs the same
    # gate. The first version of the value guard iterated `fields` only, and `label`
    # was the hole: a lone surrogate here 500ed BOTH the run PATCH and the create
    # route. Checked before `.strip()` rather than after, so the refusal describes
    # what was sent.
    if not _is_storable_value(raw, max_bytes=_MAX_LABEL_BYTES):
        return None, JSONResponse(
            status_code=422,
            content={
                "error": "unrepresentable_value",
                "key": "label",
                "keys": ["label"],
                "message": (
                    "label cannot be stored: it either contains characters that cannot "
                    "be represented in JSON, or it is longer than a name may be. "
                    "Nothing was written."
                ),
            },
        )
    cleaned = raw.strip()
    if not cleaned and not blank_is_a_choice:
        return None, JSONResponse(
            status_code=422,
            content={
                "error": "invalid_label",
                "message": (
                    "label must not be blank. Omit it to leave the current name "
                    "unchanged; a blank one names nothing and is not applied."
                ),
            },
        )
    return (cleaned or None), None


def _confirmation_required(what: str) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "confirmation_required",
            "message": f"confirmed_by_user must be true to {what}.",
        },
    )


def _confirmation_answer(value) -> str:
    """The value as the evidence entry records it. A rendering, never an invention.

    A string is recorded verbatim; anything else is rendered with a deterministic
    ``json.dumps`` so that re-submitting the same value produces the same evidence
    entry — which is what keeps a repeated write byte-stable (see
    :func:`_apply_run_field`).
    """
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


def _run_field_question(path: str) -> str:
    """The question a run-level field write records itself as answering."""
    return f"Value for {path} on this run?"


#: THE COMPLETE SET OF ``draft["fields"]`` KEYS THE RUN EDIT ROUTE MAY WRITE.
#:
#: TWO GATES, AND ONLY ONE OF THEM USED TO BE APPLIED. ``workspace.field_level``
#: answers "whose is this?" and it is a segment-aware PREFIX test — by design, so
#: that a new leaf under ``context.`` inherits its parent's classification. It is
#: NOT, and was never meant to be, an answer to "does this path exist?". Applied
#: alone it accepted ``context.typo_K``, ``context.``, ``context``,
#: ``context.<script>alert(1)</script>`` and ``timestamps.acquired_start_utc.evil``,
#: wrote each one with a fabricated ``user_confirmation`` evidence entry, and left
#: the run permanently unexportable: the official schema closes ``context``, so the
#: next check reported ``Additional properties are not allowed`` — with no way to
#: clear it from a UI that offers three fixed paths.
#:
#: SO THE SET IS DERIVED FROM ``extract.structured.FIELD_MAP``, filtered by
#: ``field_level``. FIELD_MAP is the deterministic extractor's own map of official
#: dotted paths and is therefore the vocabulary the rest of the draft pipeline
#: already speaks: every key ``draft["fields"]`` legitimately carries was put there
#: from it. Allowing exactly what the extractor can produce means this route can
#: never write a KEY the rest of the application cannot read, validate or export.
#:
#: THAT SENTENCE SAID "a key" WITHOUT THE EMPHASIS, AND THE MISSING WORD WAS A REAL
#: GAP. Read as a statement about values it is FALSE, and the false reading is what it
#: invited: the comprehension below iterates ``FIELD_MAP.values()`` and DISCARDS the
#: coercer, so nothing about the extractor's type discipline survives into this route.
#: ``context.temperature_K``'s coercer is ``_to_number`` — the extractor could never
#: emit ``"hot"``, ``{"a": 1}``, ``[1, 2]``, ``true`` or ``NaN`` there — and this route
#: accepted all five. Four are caught downstream by the official schema
#: (``'hot' is not of type 'number'``); ``NaN`` was not caught anywhere, and it
#: committed a write, 500ed the response, wedged both run reads and drove an
#: unparseable "official record" through the export gate with a PASS verdict. The
#: value-side guard is now in the PATCH route (``_is_storable_value``), NOT here,
#: because this set is a set of paths and should stay one.
#:
#: WHY NOT THE OFFICIAL SCHEMA DIRECTLY, since it is the truth plane. Because it
#: cannot enumerate a closed set of dotted paths: ``sample.composition.*``,
#: ``sample.geometry.*`` and ``system.configuration.*`` are OPEN namespaces that
#: declare no ``properties`` at all, so a schema walk would either admit any
#: invented key under them or need a second, per-subtree policy — a second
#: definition of "which fields exist". It remains the authority on SHAPE, and the
#: two agree: ``test_every_run_writable_path_resolves_to_a_typed_node_in_the_official_schema``
#: measures that every path below resolves to a typed schema node, rather than
#: trusting FIELD_MAP's comment that says so.
#:
#: FAIL-CLOSED. A field a future extractor emits is not writable here until
#: somebody classifies it, which is the same default ``field_level`` already takes.
RUN_WRITABLE_FIELD_PATHS: frozenset[str] = frozenset(
    path
    for path, _coercer in EXTRACTOR_FIELD_MAP.values()
    if ws.field_level(path) == ws.LEVEL_RUN
)


#: THE COMPLETE SET OF NAMESPACED ADDRESSES A RUN MAY RECORD AN OVERRIDE AT.
#:
#: The mirror image of :data:`RUN_WRITABLE_FIELD_PATHS`, derived the same way and for
#: the same reason. An override displaces an INHERITED value, so the admissible set is
#: the experiment-level half of the split rather than the run-level half.
#:
#: TWO GATES ON THE FIELD HALF, AND THE LESSON IS ALREADY WRITTEN DOWN ABOVE — read it
#: before touching this. ``field_level`` is a segment-aware PREFIX test, so on its own
#: it answers ``LEVEL_EXPERIMENT`` for ``sample.material.typo`` and for ``sample.``
#: just as readily as for ``sample.material.name``. Membership in
#: ``EXTRACTOR_FIELD_MAP`` is what makes the address a REAL official field path, and
#: both gates are applied here. Without the first gate this route would store a
#: confirmed override at a path the official schema closes, and the run would then be
#: unexportable — the same wedge ``context.typo_K`` produced on the edit route, with
#: the one difference that the clear operation below can undo it.
#:
#: THE BLOCK HALF IS FILTERED, NOT COPIED. Iterating ``EXPERIMENT_LEVEL_BLOCKS`` alone
#: would be tautological, so the comprehension runs over BOTH block tuples and lets
#: ``block_level`` decide. That is not decoration: it means moving ``tags`` from the
#: experiment tuple to the run tuple updates this set from the one place the
#: classification lives, instead of leaving a second copy of the decision here.
#:
#: FAIL-CLOSED, exactly as its sibling. An address the contract classifies as neither
#: level — ``system.configuration.*``, ``timestamps.created_utc``, ``meta``,
#: ``pending``, ``implicit``, ``links``, ``block_evidence`` — is not overridable until
#: somebody decides, and it is never guessed into a level here.


#: Largest page ``GET /experiments/{id}/runs`` will return in one response.
#:
#: (This block used to run straight on from the one above with no blank line, which
#: made one contiguous comment: ``RUN_PAGE_MAX`` was documented by the overridable-
#: address prose, and ``EXPERIMENT_OVERRIDABLE_ADDRESSES`` was left with no doc
#: comment at all. In this codebase these blocks ARE the documentation.)
#:
#: A CEILING ON ONE RESPONSE, NOT A LIMIT ON HOW MANY RUNS A RECORD MAY HAVE. That
#: distinction is the whole design: the route's own description promises there is no
#: limit on runs, and paging must not quietly become one. ``total`` is always the
#: count that EXIST, and a client may walk the whole list.
#:
#: WHY 200, STATED AS WHAT THE MEASUREMENT ACTUALLY SUPPORTS.
#: ``docs/run-scale-measurements.md`` records the envelope: ~100 runs load comfortably
#: (~1.1 s), 250 is noticeable (~2.2 s), 500 is bad (~4 s). **200 was not measured** —
#: no benchmark row exists for it — and it is NOT "inside the comfortable band", which
#: that table ends at 100. It sits between comfortable and noticeable, deliberately:
#: this is the worst case a single client request may ask for, not the page a UI
#: should request. An earlier revision of this comment claimed the comfortable band
#: and is corrected here, because the choice is defensible without the overstatement.
#:
#: OMITTING ``limit`` STILL RETURNS EVERYTHING, deliberately. Every existing caller —
#: and every existing test — reads the whole list, and silently truncating them to a
#: page would turn "this record has 300 runs" into "this record has 200 runs" across
#: surfaces that never opted in. Paging is something a client asks for. Guarded by
#: ``test_omitting_limit_returns_MORE_THAN_ONE_PAGE_of_runs``, which exists because
#: the five-run test that came first could not tell a default of 200 from no default.
RUN_PAGE_MAX: int = 200

#: THE BOUND IS INTERPOLATED, NOT RETYPED. Writing "1–200" as a literal here would be
#: a second copy of ``RUN_PAGE_MAX``, free to drift from it silently — and the copy
#: that drifts is the one published in the OpenAPI document, where a reader has no way
#: to check it against the constant. Changing the constant now changes the sentence.
_RUN_LIMIT_DESC = (
    f"Maximum runs to return, 1–{RUN_PAGE_MAX}. OMIT to return every run: this "
    "parameter bounds one response, and is never a limit on how many runs a record "
    "may have. `total` always reports how many exist."
)

_RUN_OFFSET_DESC = (
    "How many runs to skip, in canonical order. An offset past the end is CLAMPED to "
    "an empty page rather than refused — that is what a 'load more' sends after a "
    "concurrent delete shortened the list, and `total` tells the client it ran off "
    "the end."
)

#: Longest ``q`` the run list accepts, enforced by the route as a `422`.
#:
#: A BOUND ON WHAT IS SCANNED, refused before the scan rather than during it. The
#: match is a substring test run against every run in the record, so the work is
#: proportional to `runs x len(q)`, and an unbounded `q` is a way to make the server
#: do arbitrary work for a query nothing can satisfy.
#:
#: 200 IS SET AGAINST WHAT IS ACTUALLY SEARCHED: a run id and a record id are 26
#: characters, and a label is capped at `_MAX_LABEL_BYTES` (512). So the only thing
#: this ceiling gives up is quoting the WHOLE of an unusually long label — and any
#: substring of that label still finds it, which is what a search box is for.
RUN_QUERY_MAX = 200

_RUN_QUERY_DESC = (
    "Case-insensitive search: a substring of a run's LABEL, or a WHOLE run id or "
    "record id, or — when the whole query is digits — an exact match on the run's "
    "number. Ids match whole rather than by substring because they are ULIDs: runs "
    "created together share a ~10-character prefix, so a substring test against an "
    "id matched every run in the record. Literal text only: no regex, no fuzzy "
    "matching, no ranking, and no searching of scientific values. Omitted or blank "
    "filters nothing. Results stay in canonical run order; `matched` reports how "
    "many the query selected and `total` still reports how many runs EXIST."
)

_RUN_OVERRIDES_DESC = (
    "`any` for runs holding at least one recorded override, `none` for runs holding "
    "none. Omit to filter nothing on this axis."
)

_RUN_EXPORTED_DESC = (
    "`true` for runs that have been exported to an official record, `false` for runs "
    "that have not. Omit to filter nothing on this axis."
)

#: What makes a ``q`` a RUN NUMBER as well as a substring.
#:
#: ``str.isdigit()`` is deliberately not what this is: it is true of ``"٣"`` and of
#: ``"²"``, and ``int()`` accepts both — so a query nobody could read as "run 3"
#: would select run 3. The grounded rule is the ASCII numerals a scientist types on
#: the way to "show me run 12", and this pattern is that rule stated exactly.
_ASCII_DIGITS_ONLY = re.compile(r"[0-9]+")


def _run_matches_query(run: "ws.Run", needle: str, ordinal: int | None) -> bool:
    """Whether one run matches ``q``. A LITERAL SUBSTRING TEST, and nothing more.

    WHAT IS SEARCHED IS THE RUN'S IDENTIFIERS, NOT ITS SCIENCE — its label, its id,
    and its record id when it has one. A run's own fields, its inherited
    resolutions and its evidence are deliberately excluded. Matching on a measured
    value would make membership of the result set depend on a classification this
    server has no grounds to make, which is the project's no-guessing rule applied
    to search; it would also mean every keystroke resolved inheritance for every
    run, turning a list into a full evaluation.

    THERE IS NO INJECTION SURFACE HERE, and that is worth stating rather than
    leaving to be inferred from its absence: runs live inside the experiment's
    state document, not in a table, so ``q`` is never interpolated into SQL and
    ``%`` and ``_`` are not wildcards to escape. It is never compiled as a regex
    either — the test is Python's ``in`` over two plain strings — so ``.*``,
    ``[``, ``(``, ``?``, a quote and a backslash are ordinary characters that match
    only themselves. A scientist searching for a label containing ``(`` finds that
    label, and a query of ``.*`` matches the runs whose text literally contains
    ``.*``, which is normally none of them.

    IT RETURNS A BOOLEAN, NEVER A SCORE. Ranking by relevance would mean the run at
    a given offset changed with what was typed, and paging over a list that
    re-orders itself is how a client loses rows between pages. Canonical order is
    the contract, and the caller keeps it.

    IDS MATCH WHOLE, LABELS MATCH BY SUBSTRING, AND THAT ASYMMETRY IS THE FIX FOR A
    MEASURED DEFECT. An adversarial review found that ``q=1`` returned 120 runs of
    120 — and so did ``0``, ``01`` and ``z``. The cause is what a ULID IS: 26
    Crockford-base32 characters whose leading ~10 encode the millisecond, so every
    run created in one session shares that prefix, and its alphabet makes most
    single characters near-certain to appear somewhere in all of them. A substring
    test against an id is therefore not a weak search, it is a match-everything.

    A MINIMUM QUERY LENGTH DOES NOT FIX IT, which is why it was not chosen: the
    shared prefix is ~10 characters, so any threshold short enough to accept a
    partial paste is still long enough to match every run in the record.

    So an id is compared WHOLE. That is also what the affordance actually is — a
    human does not mean a fragment of a ULID, they paste one they copied, and a
    pasted id still matches with surrounding whitespace and in any case because the
    caller trims and case-folds before this runs. Labels keep substring matching
    because a label is prose a scientist wrote, where "300 K" genuinely is a
    fragment of something they might type.

    THE ORDINAL RULE IS WHAT MAKES SHORT QUERIES USEFUL, and it was already correct
    and simply being swamped: ``q=1`` now finds run 1 by number, plus any label
    containing "1", instead of the whole record.
    """
    if needle in run.label.lower():
        return True
    # Whole-id equality, never a substring — see the docstring. `needle` is already
    # trimmed and lowercased by the caller, so a pasted id matches in any case and
    # with surrounding whitespace.
    if needle == run.id.lower():
        return True
    if run.record_id is not None and needle == run.record_id.lower():
        return True
    return ordinal is not None and run.ordinal == ordinal


def _select_runs(
    ordered: "list[ws.Run]",
    *,
    q: str | None,
    overrides: str | None,
    exported: bool | None,
) -> "list[ws.Run]":
    """``ordered``, narrowed by the search and the filters, IN THE ORDER GIVEN.

    THE AXES ARE INDEPENDENT AND COMBINE WITH ``AND``. They are three parameters
    rather than one repeated ``filter=`` enum precisely so that contradictory
    requests are not expressible: there is no way to spell "overridden and not
    overridden", because the axis holds one value.

    A BLANK ``q`` IS AN ABSENT ``q``, NOT A QUERY THAT MATCHES NOTHING. A search box
    empties itself between keystrokes, and answering the empty box with an empty
    list would tell a scientist their record has no runs. Whitespace is trimmed for
    the same reason a trailing space in a pasted id must not lose the match.

    "HOLDS AN OVERRIDE" IS READ FROM STORED STATE — ``run.overrides``, the dict
    ``set_run_override`` writes — and is NOT recomputed by resolving every run.
    ``_resolution_state`` reports ``overridden`` for exactly the addresses in this
    dict, so resolving would answer the same question at the cost of deep-copying
    every inherited payload of every run in the record. There is one divergence, and
    it falls the honest way: an override persisted at an address ``parse_address``
    cannot parse is skipped by ``resolve_inherited`` but counted here. The run does
    hold a recorded override — it is merely unclassifiable — and ``overrides=none``
    must not file it under "nothing to see".
    """
    selected = ordered
    if overrides is not None:
        want = overrides == "any"
        selected = [run for run in selected if bool(run.overrides) is want]
    if exported is not None:
        selected = [run for run in selected if (run.record_id is not None) is exported]

    trimmed = (q or "").strip()
    if trimmed:
        ordinal = int(trimmed) if _ASCII_DIGITS_ONLY.fullmatch(trimmed) else None
        needle = trimmed.lower()
        selected = [run for run in selected if _run_matches_query(run, needle, ordinal)]
    return selected


EXPERIMENT_OVERRIDABLE_ADDRESSES: frozenset[str] = frozenset(
    [
        ws.field_address(path)
        for path, _coercer in EXTRACTOR_FIELD_MAP.values()
        if ws.field_level(path) == ws.LEVEL_EXPERIMENT
    ]
    + [
        ws.block_address(key)
        for key in (*ws.EXPERIMENT_LEVEL_BLOCKS, *ws.RUN_LEVEL_BLOCKS)
        if ws.block_level(key) == ws.LEVEL_EXPERIMENT
    ]
)


#: The exact call Starlette's ``JSONResponse.render`` makes, transcribed rather than
#: approximated — ``json.dumps(content, ensure_ascii=False, allow_nan=False,
#: indent=None, separators=(",", ":")).encode("utf-8")``.
#:
#: THE FIRST VERSION OF THIS GUARD OMITTED ``ensure_ascii=False`` AND THE ``.encode``,
#: while its comment claimed it was "the SAME function Starlette renders responses
#: with, so a value that passes here cannot fail there". That was false in a way the
#: comment made hard to doubt. With ``ensure_ascii`` at its default of ``True`` a lone
#: surrogate is escaped to ``"\ud800"`` and serialises happily; with
#: ``ensure_ascii=False`` the ``.encode("utf-8")`` raises ``UnicodeEncodeError``. So
#: ``{"context.temperature_K": "\ud800"}`` — reachable from any client that writes the
#: escape, though not from ``JSON.stringify`` — still produced a 500.
#:
#: Nothing was written and nothing was wedged in that case (the signature hash raises
#: before ``save_versioned`` writes), which is why it was an Important rather than a
#: repeat of the ``NaN`` Critical. It is fixed by making the claim true instead of by
#: narrowing the claim.
def _render_exactly_as_a_response_would(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":")
    ).encode("utf-8")


#: The deepest nesting a stored run-level value may carry.
#:
#: MEASURED, not picked. All five members of :data:`RUN_WRITABLE_FIELD_PATHS` are
#: declared ``string`` or ``number`` scalars by ``schema/isaac_record_v1.json``, and the
#: deepest WHOLE DOCUMENT anywhere in this repository — every committed record and every
#: fixture — nests 7 levels. 32 is therefore more than four times the deepest real
#: document and unreachable by any shape the schema declares at these paths, while
#: sitting far below the depth at which CPython's recursion limit is reached.
#:
#: IF THIS GUARD IS EVER REUSED FOR ANOTHER FIELD SET, re-derive it. The vendored schema
#: contains eight free-form ``type: object`` subschemas that declare no ``properties`` —
#: ``sample.composition``, ``system.configuration``,
#: ``context.transport.feed.partial_pressures``, ``measurement.series.items.conditions``
#: and ``assets.items.citation`` among them — where the instance depth a valid record may
#: carry is UNBOUNDED. 32 is measured headroom for the five run-level scalars and nothing
#: more.
_MAX_VALUE_DEPTH = 32

#: The largest a single stored run-level value may serialise to, in bytes.
#:
#: THE DEPTH CAP ALONE WAS THE THIRD NARROW GUARD IN A ROW, and a reviewer measured why:
#: at perfectly LEGAL depth, a 3-wide tree amplifies ~17-23x on the way to disk, because
#: the document is stored pretty-printed and the value is carried in an evidence
#: envelope. Measured on this build — a **236 KB body wrote 4.1 MB**, 2.1 MB wrote
#: 45.6 MB, and 172 MB wrote 4 GB while holding ``record_lock`` for 184 s and taking
#: process RSS to 5.6 GB. An 8 MB ``label`` was likewise accepted. Nothing was corrupted
#: and no verdict was falsified, so it is resource exhaustion rather than a wedge — on a
#: pod whose workspace is an ``emptyDir`` this project does not own.
#:
#: 64 KiB is ~2,000x the longest value the schema can legitimately put at any of the five
#: writable paths: all five are declared ``string`` or ``number`` scalars, and the longest
#: plausible one is a 32-character ISO-8601 timestamp with an offset. It is also a quarter
#: of ``csv_ingest.MAX_BODY_BYTES`` (256 KiB) and an eighth of
#: ``MAX_VALIDATE_RECORD_BYTES`` (512 KiB), the two limits this repository already
#: enforces — deliberately in their style rather than as a new kind of number.
_MAX_VALUE_BYTES = 64 * 1024

#: The largest ONE corrected value on `POST /edit` may serialise to. Deliberately much
#: larger than `_MAX_VALUE_BYTES`: a reduced spectrum is legitimately big, so the run
#: path's 64 KiB would refuse real science. This bounds a pathological payload — 20,000
#: series entries (~4 MB) were previously accepted and written while holding `record_lock`
#: — without pretending to be a scientific limit.
_MAX_CORRECTION_BYTES = 8 * 1024 * 1024

#: A label renders on one line of a card header, and the server's own form is
#: ``Run <ordinal>``. The longest label anywhere in this repository's fixtures is 76
#: characters. 512 bytes is generous for a name a person types and refuses the 8 MB one.
_MAX_LABEL_BYTES = 512


def _value_depth_within(value, limit: int) -> bool:
    """Is ``value`` nested no deeper than ``limit``?

    ITERATIVE ON PURPOSE. A depth-COMPUTING recursive walk — ``1 + max(depth(child) …)``,
    the shape most people reach for — would hit the same ``RecursionError`` it exists to
    prevent, on the same input, and a guard that crashes on the attack it guards against
    is not a guard.

    COST, STATED CORRECTLY. It returns at the first node past ``limit``, so a DEEP payload
    costs O(limit) — measured at 0.00 s for 200,000 levels. It is NOT bounded for a BROAD
    payload: a legal-depth tree with 43 million leaves took ~12 s in the walk alone, which
    an earlier version of this docstring denied by claiming the cost was "bounded by
    ``limit`` and not by the size of a hostile payload". That is what
    :data:`_MAX_VALUE_BYTES` is for, and it is why size is a separate condition rather
    than something this function was stretched to cover.
    """
    stack = [(value, 0)]
    while stack:
        node, level = stack.pop()
        if level > limit:
            return False
        if isinstance(node, dict):
            stack.extend((child, level + 1) for child in node.values())
        elif isinstance(node, (list, tuple)):
            stack.extend((child, level + 1) for child in node)
    return True


def _is_storable_value(value, *, max_bytes: int = _MAX_VALUE_BYTES) -> bool:
    """Can the application BUILD AND RETURN a view of this value, and store it?

    THE CONTRACT WAS TOO NARROW ONCE AND THE COST WAS A SECOND WEDGED-RECORD DEFECT, so
    it is stated as broadly as it is actually relied upon. This function used to be
    ``_is_json_renderable`` and its docstring promised only that the SERIALIZER could
    render the value. That was true, and insufficient:
    ``{"context.temperature_K": [[[…800 deep…]]]}`` renders fine — ``json.dumps``
    handles thousands of levels — and then ``_run_view`` raised ``RecursionError``
    while CONSTRUCTING the response, after the write had committed. Same four
    consequences as the ``NaN`` case: a committed write reported as a 500, an ETag that
    could not be re-read, and every read of that record 500ing permanently, on disk,
    across a process restart.

    THREE conditions, all necessary — and the count has gone 1 -> 2 -> 3 across three
    reviews, each time because the guard protected something narrower than the
    application relies on. The contract is stated as **bounded size, bounded depth, and
    renderable**, so a fourth narrowing has to argue with this sentence:

    1. **Depth** (:data:`_MAX_VALUE_DEPTH`) — bounds every recursive walk the value will
       later be subjected to: ``_run_view``, ``copy.deepcopy``, the signature hash, the
       draft validator, the exporter. A serializer test cannot express it.
    2. **Renderability** — a real render with the exact kwargs Starlette uses, so
       ``NaN``, ``Infinity`` and lone surrogates are refused. Deliberately a render
       rather than an ``isinstance`` walk: a hand-written type check would be a second,
       drifting definition of "storable".
    3. **Size** (:data:`_MAX_VALUE_BYTES`, or ``max_bytes``) — measured on the RENDERED
       bytes, which is free because condition 2 has already produced them. Bounds the
       ~17-23x amplification to disk and the time ``record_lock`` is held.

    All three are checked BEFORE the write. None is a schema check: the official schema
    still decides whether a well-formed value is the right one.

    WHAT THIS DOES NOT BOUND, stated rather than implied: the REQUEST BODY. Starlette
    allocates it in full before any of this runs, so a large body still costs memory
    once. The two read-only routes that need that guarantee use
    :func:`_read_bounded_body` over ``request.stream()``; wiring it in here means
    replacing ``Body(...)`` with a raw ``Request`` read on both write routes, a real
    change to their documented request-body handling that is deliberately NOT smuggled
    into a fix commit. The severe half — unbounded bytes reaching DISK and an unbounded
    hold on ``record_lock`` — is closed here.
    """
    if not _value_depth_within(value, _MAX_VALUE_DEPTH):
        return False
    try:
        rendered = _render_exactly_as_a_response_would(value)
    except (ValueError, TypeError, UnicodeEncodeError):
        return False
    return len(rendered) <= max_bytes


def _apply_run_field(fields: dict, path: str, value, timestamp: str) -> bool:
    """Write (or clear) ONE run-level field. Returns whether anything changed.

    A ``null`` CLEARS the field by REMOVING the key. Not by leaving a null-valued
    envelope behind: the project's rule is that a field nobody supplied stays
    absent, and an envelope carrying ``value: null`` is a present field with no
    value, which is a different statement and one a reader has to interpret.

    Every other write records a ``user_confirmation`` evidence entry alongside the
    evidence the envelope already carries — the same envelope shape and the same
    ``source_type`` the existing draft completion path uses (``complete.py``), so a
    value written here is subject to the same no-guessing checks as any other. No
    value is ever invented: only what the caller literally supplied is written.

    IT IS IDEMPOTENT, and that is a requirement rather than a nicety. The evidence
    entry carries a timestamp, so appending one unconditionally would make a
    re-submission of the SAME value change the document, bump the run's ``rev`` and
    destroy `save_versioned`'s byte-stable no-op. Re-applying a value this envelope
    already records with an equal user confirmation therefore leaves it untouched —
    exactly the idempotence `Experiment.set_run_override` documents for an override.
    """
    existing = fields.get(path)
    if value is None:
        if path in fields:
            del fields[path]
            return True
        return False

    if isinstance(existing, dict):
        prior_evidence = [e for e in (existing.get("evidence") or []) if isinstance(e, dict)]
    else:
        prior_evidence = []
    answer = _confirmation_answer(value)
    question = _run_field_question(path)
    already = (
        isinstance(existing, dict)
        and existing.get("value") == value
        and existing.get("status") == "verified"
        and any(
            e.get("source_type") == "user_confirmation"
            and e.get("question") == question
            and e.get("answer") == answer
            for e in prior_evidence
        )
    )
    if already:
        return False

    envelope = {
        "value": value,
        "status": "verified",
        "evidence": [*prior_evidence, user_confirmation(question, answer, timestamp)],
    }
    # A unit already on the envelope is CARRIED, never re-derived and never dropped:
    # it is evidence-bearing content this request said nothing about.
    if isinstance(existing, dict) and existing.get("unit") is not None:
        envelope["unit"] = existing["unit"]
    fields[path] = envelope
    return True


@router.get(
    "/experiments/{experiment_id}/runs",
    tags=[TAG_EXPERIMENTS],
    summary="List a Record's Runs",
    description=(
        "Lists this record's runs in their canonical order, each with its own "
        "draft fields, its resolved view of the record-level values it inherits, "
        "and its own revision metadata. Read-only.\n\n"
        "A run is one measurement condition and exports to exactly one official "
        "ISAAC record. Inherited record-level content is resolved on read and "
        "reported separately from the run's own fields — it is never copied down "
        "into a run, so editing a record-level value flows through to every run "
        "that has not overridden it.\n\n"
        "The `ETag` header and `experiment_version` carry the RECORD's current "
        "revision, which is what adding a run requires in `If-Match`. Each run "
        "additionally carries its own `version`, which is what editing that run "
        "requires.\n\n"
        "`q`, `overrides` and `exported` narrow the list ON THE SERVER, so finding "
        "one run never requires downloading all of them. They combine with `AND`, "
        "and paging applies to what they matched: `matched` is how many runs the "
        "query selected and `total` remains how many runs EXIST, so a client can "
        "always say \"3 of 240 runs match\" without a second request. `q` is a "
        "case-insensitive search over a run's label by substring, and over a whole "
        "run id or record id — plus its number when the query is digits. Ids match "
        "whole because they are ULIDs sharing a timestamp prefix, so a substring "
        "matched everything. It is not a regex, "
        "it does not rank, and it does not search scientific values: no measured "
        "quantity is classified here."
    ),
    # THIS PARAGRAPH IS A TWO-FILE EDIT, and the coupling is deliberate rather than
    # accidental. `apps/web/src/test/apiFixtures.ts` holds a hand-transcribed copy of
    # every operation `description`, and `test_contract_description_parity.py` fails
    # the moment the two disagree — so the search prose was added HERE and THERE in
    # one change. The alternative considered and rejected was leaving the operation
    # silent and documenting `q`/`overrides`/`exported` only on the parameters: the
    # parameters do carry their own full descriptions, but a reader of the Settings
    # API browser meets the OPERATION first, and an operation whose prose describes
    # only an unbounded read understates what the endpoint now does.
    response_description=(
        "The record's runs in canonical order, with the record's current revision "
        "and `ETag`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_TUTORIAL_SCOPE},
)
def list_runs(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    limit: Annotated[int | None, Query(ge=1, le=RUN_PAGE_MAX, description=_RUN_LIMIT_DESC)] = None,
    offset: Annotated[int, Query(ge=0, description=_RUN_OFFSET_DESC)] = 0,
    q: Annotated[
        str | None, Query(max_length=RUN_QUERY_MAX, description=_RUN_QUERY_DESC)
    ] = None,
    overrides: Annotated[
        Literal["any", "none"] | None, Query(description=_RUN_OVERRIDES_DESC)
    ] = None,
    exported: Annotated[bool | None, Query(description=_RUN_EXPORTED_DESC)] = None,
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    # ONE ETag NOW COVERS MANY DIFFERENT REPRESENTATIONS, and that is a trap for the
    # next person rather than a bug today. It is the EXPERIMENT's tag, so `limit=1&
    # offset=0` and `limit=1&offset=1` return the same tag over different runs.
    # Harmless while nothing reads `If-None-Match` here — and query strings key HTTP
    # caches separately — but `GET /experiments/{id}` a few hundred lines up already
    # implements the conditional GET someone will reach for next. Extending that to
    # this route unchanged would hand a client a 304 for page 1 because it had
    # fetched page 0, and "unchanged" would be a lie. Whoever does it must fold
    # `limit`/`offset`/`q` into the tag, or not send one on a bounded read.
    response.headers["ETag"] = exp.etag()

    ordered = exp.sorted_runs()
    total = len(ordered)
    # FILTERING HAPPENS BEFORE PAGING, and it has to: a page taken first and then
    # filtered would return fewer rows than asked for while more matches sat on the
    # next page, so "no results" would depend on where the client happened to be
    # scrolled. The window below therefore indexes the MATCHED list.
    selected = _select_runs(ordered, q=q, overrides=overrides, exported=exported)
    matched = len(selected)
    # OFFSET IS CLAMPED, NOT REFUSED. An offset past the end is not a client error —
    # it is what "load more" sends after a concurrent delete shortened the list — and
    # the honest answer is an empty page with the true `total`, from which a client
    # can see it has run off the end. Refusing would turn an ordinary race into an
    # error banner. The same rule holds when a query shortened the list under a
    # client that was already paging it.
    #
    # THIS PAGING IS NOT SNAPSHOT-CONSISTENT, AND THE PREVIOUS PARAGRAPH IS THE
    # FLATTERING HALF OF THAT STORY. It reasons about the benign case — a delete
    # AFTER the client's current position, which shortens the list and yields an
    # empty page the client can see. The unflattering case is a delete BEFORE it:
    # every later run shifts up by one, so the next `offset` starts one row late and
    # a client walking pages SILENTLY SKIPS A RUN. There is no error and no duplicate
    # to notice it by. A concurrent create is the mirror image and repeats a row.
    #
    # It is not fixed here, and saying so is the point. A cursor keyed on the
    # canonical order would fix it and is a contract change; the ordinary case is a
    # single scientist reading their own record, where the window is milliseconds
    # wide. What a client CAN do today is compare `experiment_version` across pages —
    # it is returned on every one, and any run add or delete moves it — and re-read
    # from the start when it changes. That is the intended remedy, and it was
    # undocumented until an independent review named this as the most likely way the
    # slice is wrong in production.
    #
    # `apps/web` DOES dedupe by run id when appending a page, in `RunsBrowser` — and
    # this sentence is corrected rather than left alone because when it was first
    # written it was NOT TRUE. The comment shipped in the paging slice, one slice
    # ahead of the browser that implements it; at that moment the only append in the
    # frontend was a plain `[...prev, res.run]` after Add Run, and an independent
    # reader checked and found the claim unsupported. It is true as of this commit.
    # A comment asserting a behaviour a sibling slice has not landed yet is the same
    # defect class as a UI claiming a value is verified because it looks plausible.
    #
    # A QUERY MAKES THIS STRICTLY WORSE, and the honest reading is that filtering
    # widens the window rather than opening a new hole: a run edited concurrently can
    # ENTER or LEAVE the matched set between two pages, so it can be skipped or
    # repeated without any run being created or deleted at all. `experiment_version`
    # still moves on any such write, so it remains the signal a paging client should
    # watch — it is just doing more work here than it is on an unfiltered walk.
    window = selected[offset:] if limit is None else selected[offset : offset + limit]

    return {
        "runs": [_run_view(exp, run) for run in window],
        "experiment_version": exp.version_token(),
        # THE FOUR NUMBERS A BOUNDED, FILTERED LIST CANNOT BE HONEST WITHOUT. `total`
        # is the count of runs that EXIST, not the count returned and NOT the count
        # matched, so a UI showing "50 of 500" is stating a measured fact rather than
        # inferring completeness from a short page — and a query that matches nothing
        # still reports the record's true size instead of claiming it is empty.
        # `matched` is what the current `q`/filters selected, and equals `total` when
        # none were sent; keeping the two separate is what lets a client say "3 of 240
        # runs match" in one request. `returned` is stated explicitly rather than left
        # to be derived from the array's length, so a truncation bug shows up as a
        # disagreement instead of being invisible. `offset` is echoed because a client
        # that sent one and got a clamped window otherwise cannot tell which rows it
        # holds.
        "total": total,
        "matched": matched,
        "returned": len(window),
        "offset": offset,
    }


def _seed_for_new_run(exp) -> dict:
    """The draft a run being added to ``exp`` should START with.

    ``workspace.new_run`` defaults a run's draft to ``{}`` and says why: *"the caller
    that creates a run is the one that knows whether the blank-draft pending blockers
    apply."* This is that caller, and the answer has two halves.

    THE DEFECT THIS EXISTS TO CLOSE, measured over HTTP before it was written. A run
    created with an empty draft carries no blockers, so ``Experiment.pending()`` — which
    aggregates the experiment's own plus each run's own — counted zero, and the product
    said so::

        answer every question, no runs   -> pending 0 · status ready_to_export   (true)
        add one run                      -> pending 0 · status in_review
                                            workflow: complete_metadata COMPLETED,
                                                      review_evidence  COMPLETED
        POST /export                     -> ok: false · "'descriptors' is a required
                                            property"

    So the screen reported the metadata complete and the evidence reviewed, listed
    nothing to do, and could not export — for a reason no surface named. Worse, the
    answers the scientist had already given were **silently dropped from the record**:
    ``series``, ``qc``, ``assets`` and ``descriptors_outputs`` are RUN-LEVEL blocks
    (``workspace.RUN_LEVEL_BLOCKS``), so ``resolved_run_draft`` reads them off the RUN,
    and the experiment's copies stopped being part of any exported record the moment a
    run existed.

    **THE FIRST RUN ADOPTS EVERY RUN-LEVEL ADDRESS THE EXPERIMENT HOLDS — the four
    blocks, the run-level FIELDS, and the open questions.** (An earlier version of this
    sentence said "values AND open questions" while copying only the blocks; the fields
    were silently lost and the export still said `ok: true`. Naming the three kinds
    explicitly is what stops that reading again.) A zero-run experiment IS its own record (``record_id = exp.id``);
    adding the first run moves the exported identity onto that run. If nothing carried
    the content across, the act of adding a run would destroy evidenced scientific
    values a person had entered, and would drop their unanswered questions with them.
    The experiment's own pending list is carried rather than the template's, so a
    per-file ``asset`` blocker — which the template has none of, because a blank record
    names no files — survives too.

    **THE SECOND RUN IS NOT SEEDED**, and that asymmetry is the no-guessing rule rather
    than an inconsistency. Copying the experiment's series onto a second run would
    assert that two runs measured the same spectrum, which is a scientific claim this
    application has no evidence for — exactly the invention ``CLAUDE.md`` §5 forbids.
    The first run's case carries no such claim: there was one measurement, and it is the
    one the run now exports. A later run therefore starts with the run-level questions
    from :func:`experiment_repository.blank_draft`, imported rather than re-spelled so a
    fourth added there reaches a run without anybody remembering this function exists.

    Nothing is REMOVED from the experiment. This function is pure and the caller writes
    only the run. Leaving the experiment's copy in place keeps the change reversible —
    removing the run does not take the values with it — and keeps this out of the
    business of editing a document it was not asked to edit.

    **~~"The copy is inert: ``resolved_run_draft`` never reads it once a run exists."~~
    THAT SENTENCE WAS MATERIALLY FALSE, and an independent review named it as the
    sentence that made a Critical defect invisible to a reader of this function.** The
    four run-level BLOCKS are indeed not read from the experiment once a run exists —
    but ``resolved_run_draft`` merges the experiment's ``block_evidence`` onto every
    run UNCONDITIONALLY, and its ``implicit`` onto every run that has not diverged
    (``inherit=not _diverges_from_experiment(resolutions)``; one override, even a no-op
    one, withholds all of it). *An earlier version of this correction said both were
    merged "onto every run", which is the same imprecision in the other direction and
    was found by the next review.* So a correction written into ``exp.draft`` after a run
    existed put its "Correct the QC status? → valid" confirmation into the record's
    SIDECAR while the verdict itself stayed behind, and the published record asserted a
    verdict its own evidence trail denied.

    The copy is **unreachable by the record's write routes, and partially readable at
    export**. Both halves matter, which is why they are now written out. The write side
    is closed by :func:`_refuse_run_level_on_the_record`; ``Experiment.pending``
    withholds the questions, but only for a kind some run actually carries, so a
    question is never hidden from both.
    """
    if not exp.runs:
        seed: dict = {}
        exp_draft = exp.draft if isinstance(exp.draft, dict) else {}
        for block in ws.RUN_LEVEL_BLOCKS:
            if block in exp_draft:
                seed[block] = copy.deepcopy(exp_draft[block])
        # THE FIELDS TOO, NOT ONLY THE BLOCKS — and this half was missing, which an
        # independent review measured as the MORE dangerous of the two. The block half
        # failed loudly at export (`'descriptors' is a required property`), which is how
        # it was found; the field half returns `ok: true` and simply drops evidenced
        # values. Measured on a fully-evidenced record, before and after `POST /runs`:
        # `context.environment`, `context.temperature_K`,
        # `context.thermodynamics.atmosphere` and both `timestamps.acquired_*` gone from
        # the exported record, twelve sidecar evidence keys with them, export still ok.
        #
        # `field_level` is asked per key rather than iterating `RUN_LEVEL_FIELD_PATHS`,
        # because `context` is a PREFIX there and the draft's keys are full paths.
        exp_fields = exp_draft.get("fields")
        if isinstance(exp_fields, dict):
            carried = {
                path: copy.deepcopy(envelope)
                for path, envelope in exp_fields.items()
                if isinstance(path, str) and ws.field_level(path) == ws.LEVEL_RUN
            }
            if carried:
                seed["fields"] = carried
        # THE SIX `system.configuration.*` FIELDS ARE DELIBERATELY NOT CARRIED. They are
        # `unclassified` — neither experiment-level nor run-level — because whether two
        # runs of one experiment may legitimately differ in detector model is a
        # scientific question this repository has no answer to
        # (`docs/run-scope-decision-packet.md`, open for Angel). Copying them onto a run
        # would answer it by accident, in the direction that is harder to undo. The cost
        # is stated rather than hidden: on the fan-out path they are dropped from the
        # exported record, which is the pre-existing behaviour of every unclassified
        # field and is not introduced here.
        seed["pending"] = copy.deepcopy(
            [
                entry
                for entry in (exp_draft.get("pending") or [])
                if ws.blocker_is_run_level(entry)
            ]
        )
        return seed

    from .experiment_repository import blank_draft  # noqa: PLC0415 - avoids a cycle

    return {
        "pending": [
            copy.deepcopy(entry)
            for entry in blank_draft()["pending"]
            if ws.blocker_is_run_level(entry)
        ]
    }


@router.post(
    "/experiments/{experiment_id}/runs",
    tags=[TAG_EXPERIMENTS],
    status_code=201,
    summary="Add a Run to a Record",
    description=(
        "Adds one run to this record and returns it, together with the record's "
        "new revision. A run is one measurement condition and exports to exactly "
        "one official ISAAC record.\n\n"
        "Adding a run rewrites the record, so this requires the RECORD's current "
        "`ETag` in `If-Match` — omitted is `428`, malformed is `400`, and stale is "
        "`412` with nothing written.\n\n"
        "THE FIRST RUN ADOPTS THE RECORD'S PER-RUN CONTENT; A LATER RUN DOES NOT. A "
        "record with no runs is its own record, so adding the first moves the exported "
        "identity onto that run — and the spectrum, the QC verdict, the descriptors, the "
        "assets and the run-level context and timing values are read off the RUN at "
        "export. Without carrying them across, adding a run would silently remove "
        "everything already recorded from every record this one publishes. A SECOND run "
        "receives none of it: copying one run's spectrum onto another would assert that "
        "two runs measured the same thing, which nothing here evidences. Open questions "
        "travel the same way, so nothing a person still owes is lost either.\n\n"
        "Record-LEVEL values are still never copied down — they are inherited by "
        "reference at read time — and no scientific value is invented anywhere. Six "
        "`system.configuration.*` fields are carried by neither route because their "
        "scope is an open scientific question.\n\n"
        "This is refused with `409` on a record that has ALREADY been exported without "
        "runs: adding one would publish a second official record with the same science, "
        "and no operation withdraws the first.\n\n"
        "Its `label` may be supplied; when "
        "it is omitted or blank the server assigns the next `Run N`, and a label "
        "that is not a string, or one JSON cannot represent (a lone surrogate), is "
        "rejected with `422` rather than coerced.\n\n"
        "There is no limit on how many runs a record may have."
    ),
    response_description=(
        "The newly created run and the record's new revision, with the record's "
        "new `ETag`."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_TUTORIAL_SCOPE,
        **_R_PRECONDITION,
        **_R_ALREADY_EXPORTED_WITHOUT_RUNS,
    },
)
def post_run(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    body: dict | None = Body(
        default=None,
        description=(
            "`{\"label\": \"<optional string>\"}`. Omit the body entirely, omit "
            "`label`, or send a blank one, and the server assigns the next "
            "`Run N`."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The RECORD's current `ETag`, exactly as a read operation "
            "returned it — not a run's."
        ),
    ),
):
    # Existence pre-check OUTSIDE the lock, exactly as `post_edit` does it, so a
    # bogus id never pins a permanent entry in the never-evicting lock map.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        label, err = _clean_label((body or {}).get("label"))
        if err is not None:
            return err
        precondition = _check_if_match(if_match, exp)
        if precondition is not None:
            return precondition
        # ADDING A RUN TO AN ALREADY-EXPORTED ZERO-RUN RECORD IS REFUSED, and an
        # independent review is why. A zero-run record exports under its OWN id; the
        # first run moves the exported identity onto the run. Before adoption the
        # second export refused (the run had no descriptors), so the question never
        # arose. With adoption it succeeds, and the measured result was TWO official
        # ISAAC records with different ids, identical science, no `links` relation
        # between them, and nothing on any surface disclosing the duplication.
        #
        # The alternatives were considered and are worse. Pruning the earlier record
        # deletes a published artifact — and `_materialise_pending_units`' keep-set
        # protects `exp.id` unconditionally, deliberately, so that a legacy 1:1 artifact
        # survives. Emitting a link between them invents a relation the records do not
        # support. Refusing states the real constraint: the record has already been
        # published under its own identity, and this application has no operation that
        # unpublishes one.
        if not exp.runs and exp.exported():
            return JSONResponse(
                status_code=409,
                content={
                    "error": "already_exported_without_runs",
                    "experiment_id": exp.id,
                    "record_id": exp.record_id,
                    "message": (
                        "This record has already been exported under its own identity. "
                        "Adding a run would move the exported identity onto the run and "
                        "publish a second official record with the same science, and "
                        "there is no operation that withdraws the first. Nothing was "
                        "written."
                    ),
                },
            )
        run = exp.add_run(label=label, draft=_seed_for_new_run(exp))
        _changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another writer won the race; this run was not added
        # `_changed` is structurally always True here — a new run with a fresh id
        # cannot leave the authoritative signature equal — so it is not branched on.
        # `save_versioned` is what bumps the run to its first revision.
        response.headers["ETag"] = exp.etag()
        return {"run": _run_view(exp, run), "experiment_version": exp.version_token()}


@router.get(
    "/experiments/{experiment_id}/runs/{run_id}",
    tags=[TAG_EXPERIMENTS],
    summary="Read One Run",
    description=(
        "Returns one run of this record: its own draft fields, its resolved view "
        "of the record-level values it inherits, and its revision metadata. "
        "Read-only.\n\n"
        "The `ETag` header carries THE RUN's current revision, which is what "
        "editing this run requires in `If-Match` — the record's own `ETag` will "
        "not match it, and adding a run needs the record's rather than this one. "
        "Inherited content is resolved on read and is never stored on the run."
    ),
    response_description="The run, with the run's own current `ETag`.",
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_RUN_NOT_FOUND},
)
def get_run(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    run_id: RunId,
    response: Response,
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    run = exp.get_run(run_id)
    if run is None:
        return _run_not_found(experiment_id, run_id)
    response.headers["ETag"] = f'"{run.version_token()}"'
    return {"run": _run_view(exp, run)}


@router.patch(
    "/experiments/{experiment_id}/runs/{run_id}",
    tags=[TAG_EXPERIMENTS],
    summary="Edit One Run's Own Fields",
    description=(
        "Writes run-level draft values on ONE run, recording a user confirmation "
        "for each, and optionally renames it. Returns the refreshed run.\n\n"
        "Requires `confirmed_by_user: true` and THE RUN's current `ETag` in "
        "`If-Match` — not the record's. Omitted is `428`, malformed is `400`, and "
        "stale is `412` with nothing written and the run's current `ETag` echoed.\n\n"
        "Each key in `fields` must be a real official field path that is "
        "run-level. A key that is not — an invented or misspelt path such as "
        "`context.typo_K`, a record-level path such as `sample.material.name`, or "
        "one the contract assigns to neither level — is rejected with `422` naming "
        "it, and NOTHING in the request is written. It is never silently ignored, "
        "the classification is never guessed, and a path with no home in the "
        "official schema is never stored: doing so would record a confirmation for "
        "a value the schema cannot hold and would block this run's export. A "
        "`null` value clears that field by removing it; no value is ever invented, "
        "and a body that names no run-level field and no new label is rejected with "
        "`422` rather than silently doing nothing. A `label` that is blank or only "
        "whitespace is rejected the same way — omit it to leave the name "
        "unchanged.\n\n"
        "Re-submitting a value the run already records is a no-op: it rewrites "
        "nothing and does not advance the run's revision."
    ),
    response_description="The refreshed run, with the run's new `ETag`.",
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_RUN_NOT_FOUND, **_R_PRECONDITION},
)
def patch_run(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    run_id: RunId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"confirmed_by_user\": true, \"fields\": {<dotted.path>: <value>}, "
            "\"label\": \"<optional new label>\"}`. Omitting `confirmed_by_user: "
            "true`, naming a path that is not run-level, naming nothing at all, or "
            "sending a value or label JSON cannot represent (`NaN`, `Infinity`, a "
            "lone surrogate) is rejected with `422` and writes nothing."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. THE RUN's current `ETag`, exactly as a run read operation "
            "returned it — not the record's."
        ),
    ),
):
    # Existence pre-check OUTSIDE the lock, as every other mutation does. The lock is
    # per RECORD, not per run: runs live inside the record's document, so two runs of
    # one record serialise against each other, which is what makes their independent
    # `If-Match` validators safe.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        run = exp.get_run(run_id)
        if run is None:
            return _run_not_found(experiment_id, run_id)
        if body.get("confirmed_by_user") is not True:
            return _confirmation_required("edit a run")
        precondition = _check_if_match(if_match, _RunPrecondition(run, exp.id))
        if precondition is not None:
            return precondition

        raw_fields = body.get("fields")
        if raw_fields is None:
            raw_fields = {}
        if not isinstance(raw_fields, dict):
            return JSONResponse(
                status_code=422,
                content={
                    "error": "invalid_fields",
                    "message": "fields must be an object of dotted official paths.",
                },
            )
        label, err = _clean_label(body.get("label"), blank_is_a_choice=False)
        if err is not None:
            return err

        # RESOLVE EVERY KEY BEFORE WRITING ANYTHING. A request naming one key this
        # route may not write is refused whole, so a caller can never be left with a
        # partial write it was told was rejected.
        #
        # MEMBERSHIP, NOT CLASSIFICATION. `RUN_WRITABLE_FIELD_PATHS` is the derived
        # set of real official field-map paths that are the run's to write; see its
        # own comment for why a `field_level` prefix test alone admitted invented
        # paths and wedged the run's export.
        refused = [
            key
            for key in raw_fields
            if not isinstance(key, str) or key not in RUN_WRITABLE_FIELD_PATHS
        ]
        if refused:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "unrecognized_field",
                    "key": str(refused[0]),
                    "keys": [str(k) for k in refused],
                    "message": (
                        "These paths are not run-level official fields, so they "
                        "cannot be written on a run. A path that is not an official "
                        "field at all is refused rather than stored: writing one "
                        "would record a confirmation for a value with no home in the "
                        "schema, and would then block this run's export. "
                        "Record-level values are edited on the record and inherited; "
                        "a path the contract classifies as neither level is not "
                        "guessed into one."
                    ),
                },
            )
        if not raw_fields and label is None:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "unrecognized_field",
                    "key": None,
                    "keys": [],
                    "message": "No run-level field and no new label was named in the request.",
                },
            )

        # AND RESOLVE EVERY VALUE, not only every key. The filter above is key-only,
        # and that was not enough.
        #
        # THE DEFECT THIS CLOSES, measured end to end. Starlette parses the body with
        # the stdlib `json.loads`, which ACCEPTS the JavaScript-only literals `NaN`,
        # `Infinity` and `-Infinity`; it renders responses with
        # `json.dumps(..., allow_nan=False)`, which REFUSES them. So a single
        # `{"fields": {"context.temperature_K": NaN}}` — a legal key, a value no
        # browser's `JSON.stringify` can emit but `curl` can — produced ALL of:
        #
        #   * the write COMMITTED (`rev` 1 -> 2, bare `NaN` in `experiment.json`,
        #     plus a fabricated confirmation whose answer read "NaN") while the
        #     response was a 500. A successful write reported as a failure is worse
        #     than the silent no-op the comment above was written to close.
        #   * `GET .../runs` and `GET .../runs/{id}` 500ing PERMANENTLY thereafter, so
        #     a client could not even re-read the ETag it needed to repair the run.
        #   * a TRUTH-PLANE ESCAPE (`CLAUDE.md` §13): `jsonschema` accepts
        #     `float('nan')` as `"number"`, so the draft check, the official check,
        #     the export gate and `isaac validate --official` all reported PASS over a
        #     record file that no strict RFC-8259 parser will read.
        #
        # The ingress is this route and nothing else — `POST /edit` already answers
        # 422 and `POST /answers` leaves the value untouched, both measured. So the
        # guard belongs here, before the write, and it uses the SAME typed refusal the
        # key filter uses rather than inventing a second vocabulary.
        #
        # It rejects on RENDERABILITY, not on a hand-written type list: the property
        # that matters is "the response serializer and the on-disk document can
        # represent this", and `allow_nan=False` is exactly that test. A type
        # allowlist would have to be kept in step with the schema by hand, and this
        # route deliberately derives its key set rather than hand-copying it.
        unrenderable = [
            key
            for key, value in raw_fields.items()
            if not _is_storable_value(value)
        ]
        if unrenderable:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "unrepresentable_value",
                    "key": str(unrenderable[0]),
                    "keys": [str(k) for k in unrenderable],
                    "message": (
                        "These values cannot be stored. Either they cannot be "
                        "represented in JSON — `NaN`, `Infinity` and `-Infinity` are "
                        "accepted by some parsers but are not JSON, and a record "
                        "containing one could not be read back or exported — or they "
                        "nest more deeply than a stored value may. Nothing was written."
                    ),
                },
            )

        draft = run.draft if isinstance(run.draft, dict) else {}
        run.draft = draft
        # THE EMPTY MAP IS NOT ATTACHED UNTIL SOMETHING IS ACTUALLY WRITTEN.
        # `draft["fields"]` is part of the run's authoritative signature, so
        # creating it unconditionally made a request that wrote NOTHING — a `null`
        # clear of a field this run does not have — still advance the run's `rev`.
        # Nothing lied about it (the response reported the new version honestly)
        # and it was reachable once per run; it is fixed because a revision means
        # "your edit landed" and that one had not.
        existing_fields = draft.get("fields")
        fields = existing_fields if isinstance(existing_fields, dict) else {}
        timestamp = _now_iso()
        wrote = False
        for path, value in raw_fields.items():
            if _apply_run_field(fields, path, value, timestamp):
                wrote = True
        if wrote and not isinstance(existing_fields, dict):
            draft["fields"] = fields
        if label is not None:
            run.label = label

        # The client's validator is the RUN's, so it is deliberately NOT passed to
        # `_save_versioned`: a durable refusal is a statement about the RECORD's
        # document, and echoing a run version as the `expected_version` of a record
        # conflict would be two different things wearing one name. `null` is the
        # honest answer there; the record's current version is still echoed.
        _changed, stale = _save_versioned(exp, None)
        if stale is not None:
            return stale  # another writer won the race; this edit was not applied
        response.headers["ETag"] = f'"{run.version_token()}"'
        return {"run": _run_view(exp, run)}


# --- overriding ONE inherited record-level value on ONE run --------------------
#
# WHAT IS AND IS NOT AUDITED HERE, STATED WHERE A READER MEETS IT rather than left to
# be discovered. An override is meant to be an audited act, and two thirds of that is
# real: ``Override`` stores ``recorded_utc`` (when it was recorded) and ``displaced``
# (the inherited payload it displaced, deep-copied at capture, never refreshed). The
# third — WHO recorded it — IS NOT STORED, and no field is stamped with a guess.
#
# The reason is not oversight and it is not laziness. This application plumbs no
# per-request user identity at all: the edge supplies Authentik headers and ISAAC
# consumes NONE of them, and two of the seven arrived carrying the client's own value
# untouched (``docs/identity-trust-contract.md`` §6A). So there is nothing here that
# could make an actor field true. Stamping one anyway — a username read from an
# unverified header, a literal ``"user"``, the string ``"unknown"`` — would write a
# claim about a person into an audit record on no evidence, which is exactly the
# guessing this project's field-level rules exist to refuse. Absence is the honest
# encoding, the same way a missing draft value is.
#
# ADDING ONE IS A DECISION GATED ON THE IDENTITY WORK, not a follow-up ticket for
# whoever next opens this file. And it is not free even then: ``Override`` is inside
# ``_run_signature_payload``, so a new field changes the authoritative signature of
# every override already stored and bumps every affected run's ``rev`` on the next
# save. Whoever adds it owns that migration.


#: The JSON type names the vendored official schema uses, mapped to what a parsed
#: request body would actually be.
_JSON_TYPE_TO_PYTHON: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
}


@functools.lru_cache(maxsize=None)
def _official_block_type(key: str) -> str | None:
    """The JSON type the OFFICIAL SCHEMA declares for one top-level block, or ``None``.

    DERIVED, NOT HAND-WRITTEN, and the derivation is doing real work rather than
    showing off. Both overridable blocks are top-level official properties —
    ``attribution`` is declared ``object`` and ``tags`` ``array`` — and a payload of
    the wrong one is not merely invalid later, it REACHES A CRASH: the draft
    validator's attribution branch guards the server-stamped-identity check with an
    ``isinstance`` and then reads ``attribution.get("contributors")`` unguarded, so a
    LIST stored at ``attribution`` raises ``AttributeError`` inside the deterministic
    core the moment anything checks that run. That is a 500 out of the truth plane
    reached from a stored document, so the type is gated before the write.

    THE GATE IS THE BLOCK'S TOP-LEVEL TYPE AND NOTHING ELSE — stated because the
    paragraph above reads as a broader promise than it keeps. A LIST at ``attribution``
    is refused here; a DICT at ``attribution`` whose ``contributors`` is a string, a
    number, or a list of non-objects satisfies this gate completely and still reaches
    the same class of crash one level down (``draft_validator.py:286``). That second
    exposure is closed separately, by :data:`_PROBE_STRUCTURAL_ERRORS` around the probes
    in :func:`_refuse_override_payload`, and neither mechanism subsumes the other.

    Reading the schema rather than transcribing it means the gate follows a schema
    refresh instead of silently disagreeing with it. ``None`` means the schema
    declares no type for that key, which the caller treats as fail-closed — see
    :func:`_refuse_override_payload`.

    THE CACHE MAKES THE FAIL-CLOSED ANSWER STICK, and the direction is why that is
    acceptable. ``lru_cache`` memoizes ``None`` as readily as a type name, so a single
    transient ``OSError`` on the vendored schema — a file briefly unreadable during a
    deployment, say — refuses every later override of THAT KEY for the lifetime of the
    process rather than for one request, and only a restart clears it. (Per key: the
    cache is keyed on ``key``, so both block overrides are disabled only if both were
    first resolved during the outage.) That is refusing writes that would have been
    accepted, never accepting writes that should have been refused, so the worst case is
    an operation temporarily unavailable and typed ``422`` rather than a wrong-typed
    block reaching the truth plane. Not worth a cache-invalidation mechanism; worth
    saying out loud so nobody debugs it twice.
    """
    try:
        schema = json.loads(schema_path(REPO_ROOT).read_text(encoding="utf-8"))
        declared = ((schema.get("properties") or {}).get(key) or {}).get("type")
    except (OSError, ValueError):  # unreadable or unparseable vendored schema
        return None
    return declared if isinstance(declared, str) else None


#: The exceptions a CLIENT-AUTHORED payload can raise out of the deterministic draft
#: validator, caught around the two probes in :func:`_refuse_override_payload` and
#: turned into the typed 422 that function already returns.
#:
#: THIS SET IS CHOSEN, NOT SWEPT. Both members were measured, on this route, with
#: ``raise_server_exceptions=False`` — so this is what a real client saw, not what a
#: test harness re-raised:
#:
#: * ``TypeError`` — the validator iterates something a client made non-iterable.
#:   ``{"evidence": 7}`` reaches ``[e for e in (env.get("evidence") or [])]`` in
#:   ``draft_validator._check_envelope`` and raises ``'int' object is not iterable``;
#:   so does ``{"contributors": 7}`` at
#:   ``enumerate(attribution.get("contributors") or [])``.
#: * ``AttributeError`` — the validator calls ``.get`` on something a client made a
#:   non-mapping. ``{"contributors": ["not-a-dict"]}`` reaches
#:   ``name, role = c.get("name"), c.get("role")`` in the contributors loop and raises
#:   ``'str' object has no attribute 'get'``.
#:
#: THE LINE NUMBERS THAT USED TO BE HERE (``draft_validator.py:94`` and ``:286``) ARE
#: GONE ON PURPOSE. Both were already wrong before this comment was last edited — line
#: 94 in that file was blank — and a wrong citation in a comment about a fail-closed
#: branch is worse than none, because it reads as a checkable fact and is not one. The
#: enclosing FUNCTION is named instead; it survives an edit above it, which a line
#: number does not.
#:
#: Those two cover every case measured on this route, and the claim is exactly that —
#: not a proof that no third exists. It is a bounded surface: the validator was never
#: handed a client-authored envelope or block over HTTP before this operation (`/edit`
#: refuses an `attribution` answer with 422 `unrecognized_field`, and
#: `POST /api/validate/record` runs the OFFICIAL validator instead), and reading the two
#: branches it reaches finds no other unguarded structural assumption. If a third
#: appears it will appear as a 500 in the logs, which is the outcome this set is
#: deliberately shaped to keep possible.
#:
#: WHAT IS DELIBERATELY NOT CAUGHT, and why the tempting wider catch is worse. A bare
#: ``except Exception`` would convert a genuine defect in the truth plane — a
#: ``KeyError`` from a rule that forgot a guard, a ``ValueError`` from a real
#: computation, a ``RecursionError`` — into a 422 that blames the client for the
#: server's bug, and the 500 that would otherwise be investigated would never be seen.
#: Either member alone leaves the other crash live — measured by removing each guard
#: separately and running ``test_run_api.py``: the field probe alone, 6 red; the block
#: probe alone, 10 red; both, 14 red; every failure ``500 != 422``. So narrowing to one
#: member would fix half the exposure. ``RecursionError`` in particular is
#: already unreachable here — ``_is_storable_value`` caps depth above — and it is not a
#: statement about the payload's shape, so it stays a 500.
#:
#: The guard is around the CALL, not inside the validator: hardening
#: ``draft_validator.py`` is a truth-path change (``CLAUDE.md`` §13) and belongs in its
#: own slice. Nothing about the truth plane's behaviour changes here; only this route
#: stops letting its exception escape as HTTP 500.
_PROBE_STRUCTURAL_ERRORS = (AttributeError, TypeError)


def _not_overridable(address: object) -> JSONResponse:
    """A 422 naming the address, for anything that cannot carry an override.

    ONE refusal for four distinct causes, deliberately: a malformed address, a
    run-level one, one the contract classifies as neither level, and a well-formed
    record-level-LOOKING path that is not a real official field. A client's remedy is
    the same in all four — name an address from the overridable set, spelt as the run
    view spells the keys of its ``inherited`` map — so splitting them would be four
    names for one repair.

    THE QUALIFICATION IS CARRIED HERE TOO, and it is not decoration. An earlier
    revision of this docstring, and of the message below, told a client to name "an
    address the run view actually reports under ``inherited``". That is FALSE IN BOTH
    DIRECTIONS on the committed seed and was already corrected in the operation's
    OpenAPI description — but a client reading a refusal never sees that description,
    so the retracted claim survived in the one place it would actually be acted on.
    Measured: ``field:system.domain`` IS reported under ``inherited`` and is NOT
    overridable, and ``block:tags`` IS overridable and is absent from the map until the
    record carries a tag. The map is where the SPELLING is read; it is neither necessary
    nor sufficient for membership. Pinned by
    ``test_the_inherited_map_and_the_overridable_set_are_NOT_the_same_set``.
    """
    return JSONResponse(
        status_code=422,
        content={
            "error": "not_overridable",
            "address": str(address),
            "message": (
                "This address cannot hold a run override. Only a record-level value "
                "a run INHERITS can be overridden — `field:<official.dotted.path>`, "
                "`block:attribution` or `block:tags`, spelt exactly as the run's "
                "`inherited` map spells its keys. Appearing in that map is where the "
                "spelling is read, and it is neither necessary nor sufficient: "
                "`block:tags` is overridable but is absent from the map until the "
                "record carries a tag, and `field:system.domain` is reported there but "
                "is not overridable. A run's own fields are edited on "
                "the run instead, a misspelt or invented path is refused rather than "
                "stored, and an address the contract assigns to neither level is not "
                "guessed into one. Nothing was written."
            ),
        },
    )


def _refuse_override_payload(kind: str, name: str, payload: object) -> JSONResponse | None:
    """A 422 if this payload cannot be stored at this address, else ``None``.

    THREE GATES, and each one closes something measured rather than imagined.

    1. **Storable at all** — the shared :func:`_is_storable_value`, so ``NaN``,
       ``Infinity``, a lone surrogate, an absurdly nested value and an oversized one
       are refused here for the same reasons they are refused on the run edit route.
       An override payload lands in the same document, is walked by the same signature
       hash, and is rendered by the same response serializer.

    2. **The right SHAPE for the namespace.** A ``field:`` payload is a draft field
       envelope; a ``block:`` payload is the block itself.

       The envelope check is NOT re-implemented here. It runs the deterministic draft
       validator over a probe draft carrying only this field and keeps the findings
       filed against that field, so the five legal statuses, "status 'missing' but a
       value is present", "status 'verified' but value is null" and "verified field has
       no observed evidence or user confirmation" are the truth plane's own rules
       rather than a second copy of them that would drift. That last one matters most:
       it is what stops this operation storing a `verified` scientific value carrying
       no evidence, which is the whole no-guessing rule the draft format exists to
       enforce. The probe's ``meta.*`` findings are discarded — a probe draft has no
       record-type stamp and that is not this field's problem.

       The block check is the schema-declared JSON type (:func:`_official_block_type`),
       fail-closed when the schema declares none. It is the block's TOP-LEVEL type only
       — see that function on why the contents need a second guard.

       NEITHER PROBE MAY ESCAPE AS A 500, and it took a review to notice that both did.
       The validator makes structural assumptions this route is the first HTTP caller to
       hand a client-authored value against, so a wrong-shaped payload — ``evidence`` a
       bare number, ``contributors`` a string or a list of non-objects — raised out of
       the deterministic core and rendered as HTTP 500 on 14 of the 15 admissible
       addresses. Both probes are now wrapped in :data:`_PROBE_STRUCTURAL_ERRORS`, which
       documents the exception set and what it deliberately does not catch, and a
       malformed payload falls through to the typed 422 this function already returns.
       Worth being exact about what that defect was NOT: nothing was stored, the
       workspace stayed byte-identical, and the record stayed readable — unlike the
       ``NaN`` and depth defects gate 1 exists for, which committed first and then
       permanently 500ed every subsequent read.

    3. **The server-stamped identity is refused even inside a block.** ``attribution``
       is overridable and ``attribution.uploaded_by`` is a field no client may author:
       the schema declares it stamped from an authenticated identity, and this
       application has none to stamp it with. The refusal is the draft validator's own
       — the same probe, filtered to that one finding — so this route holds a reference
       to the rule and not a copy of it. It is checked AFTER the type gate on purpose:
       the validator's attribution branch would raise on a non-dict.

    WHAT THIS DOES NOT DO. It does not decide whether the value is scientifically
    right, and — stated more accurately than an earlier revision of this docstring,
    which said only "the block-evidence coverage checks" — it applies NO
    ``attribution.contributors[...]`` finding at all, SHAPE OR EVIDENCE. The block probe
    is filtered to ``UPLOADED_BY_PATH``, so every finding filed against a contributor
    index is dropped, including the two shape refusals the validator does reach:
    measured, ``{"contributors": [{}]}`` and
    ``{"contributors": [{"name": ["a"], "role": "b"}]}`` are both STORED with 200, and
    the run check then reports ``ok: false`` over each — the first "contributor missing
    name/role — cannot key its evidence", the second "contributor has no evidence"
    (a list-valued ``name`` is truthy, so it passes the name/role check and is then keyed
    under something nothing covers). Both are removable by the clear operation.

    That is deliberate for the evidence half: coverage legitimately depends on evidence
    the EXPERIMENT carries — a contributor's provenance lives in the experiment's
    ``block_evidence``, which a probe draft holding one block does not have — so running
    it here would refuse a perfectly good override for evidence that is present. The
    shape half rides along with it, and the posture is the same either way: the run check
    and the export gate remain the authority, and an
    override they refuse is stored, visible, refused at the gate, and removable by the
    clear operation below. That is the same posture as any other unfinished draft
    content, and it is fail-closed at the boundary that mints an official record.
    """
    if not _is_storable_value(payload):
        return JSONResponse(
            status_code=422,
            content={
                "error": "unrepresentable_value",
                "address": (
                    ws.field_address(name)
                    if kind == ws.ADDRESS_FIELD
                    else ws.block_address(name)
                ),
                "message": (
                    "This override cannot be stored. Either it cannot be represented "
                    "in JSON — `NaN`, `Infinity` and `-Infinity` are accepted by some "
                    "parsers but are not JSON, and a record containing one could not "
                    "be read back or exported — or it nests more deeply, or is larger, "
                    "than a stored value may. Nothing was written."
                ),
            },
        )

    if kind == ws.ADDRESS_FIELD:
        where = f"fields.{name}"
        try:
            findings = [
                message
                for at, message in validate_draft({"fields": {name: payload}}).errors
                if at == where
            ]
        except _PROBE_STRUCTURAL_ERRORS:
            # QUOTED from `draft_validator.py:186`, which files exactly this finding for
            # a payload that is not a dict at all. A dict whose `evidence` is a bare
            # number gets PAST that guard and then crashes inside the envelope check, so
            # the same words are the honest answer for the same reason: this is not a
            # field envelope. It is a quotation in a refusal message, not a second copy
            # of a rule — nothing branches on it.
            findings = ["must be a field envelope"]
        if findings:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "invalid_envelope",
                    "address": ws.field_address(name),
                    "findings": findings,
                    "message": (
                        "A record-level field override must be a draft field envelope "
                        "— `{\"value\": …, \"status\": …, \"evidence\": [ … ]}` — and "
                        "this one is not one the no-guessing rules accept. The "
                        "findings are the deterministic draft validator's own words. "
                        "Nothing was written."
                    ),
                },
            )
        return None

    declared = _official_block_type(name)
    expected = _JSON_TYPE_TO_PYTHON.get(declared or "")
    # `bool` is a subclass of `int`, so it satisfies an `integer`/`number` check it has
    # no business satisfying. Excluded unless the schema actually declared `boolean`.
    if (
        expected is None
        or not isinstance(payload, expected)
        or (declared != "boolean" and isinstance(payload, bool))
    ):
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_block_payload",
                "address": ws.block_address(name),
                "expected_type": declared,
                "message": (
                    "A record-level block override must be the block itself, of the "
                    "type the official schema declares for it — an object for "
                    "`attribution`, an array of labels for `tags`. A payload of "
                    "another type is refused rather than stored: it has no valid "
                    "shape in an exported record, and the deterministic checks that "
                    "read it are entitled to assume the declared one. Nothing was "
                    "written."
                ),
            },
        )

    try:
        identity_findings = [
            message
            for at, message in validate_draft({name: payload}).errors
            if at == UPLOADED_BY_PATH
        ]
    except _PROBE_STRUCTURAL_ERRORS:
        # THE PROBE COULD NOT REACH A VERDICT, so nothing it would have checked may be
        # treated as cleared. The crash site is AFTER the server-stamped-identity
        # refusal is filed, so a raise discards a report that may have carried it —
        # this cannot degrade to "no findings, store it". Refused, and the body does
        # NOT carry a `findings` key, because there are none: every `findings` list this
        # route returns is the validator's own words and an invented one would break
        # that. Measured shape: `attribution.contributors` must be a list of
        # contributor objects.
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_block_payload",
                "address": ws.block_address(name),
                "expected_type": declared,
                "message": (
                    "This block override is the type the official schema declares, but "
                    "its CONTENTS are not a shape the deterministic checks can read — "
                    "`attribution.contributors` must be a list of contributor objects, "
                    "each an object. It is refused rather than stored: the checks that "
                    "would have run over it could not reach a verdict, so nothing in it "
                    "is treated as cleared. Nothing was written."
                ),
            },
        )
    if identity_findings:
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_block_payload",
                "address": ws.block_address(name),
                "expected_type": declared,
                "findings": identity_findings,
                "message": (
                    "This block override names a field no client may author. The "
                    "finding is the deterministic draft validator's own words. "
                    "Nothing was written."
                ),
            },
        )
    return None


def _override_address(body: dict) -> tuple[str, str, str] | None:
    """``(address, kind, name)`` for an admissible address, else ``None``.

    BOTH GATES, in the order that makes the second safe: membership in
    :data:`EXPERIMENT_OVERRIDABLE_ADDRESSES` first, which is what makes
    ``parse_address`` below unable to raise — every member is well-formed by
    construction, because every member was BUILT by ``field_address`` or
    ``block_address``.
    """
    address = body.get("address")
    if not isinstance(address, str) or address not in EXPERIMENT_OVERRIDABLE_ADDRESSES:
        return None
    kind, name = ws.parse_address(address)
    return address, kind, name


#: The question text stored on a contributor's ``user_confirmation`` evidence entry.
#:
#: IT NAMES THE OPERATION AND REFUSES TO NAME THE PERSON. What this application can
#: honestly assert is that a request arrived at ONE named operation carrying
#: ``confirmed_by_user: true`` and this contributor in its payload. WHO sent it is not
#: recorded, because no trusted authentication boundary exists to read an identity from
#: (``CLAUDE.md`` §15; the same reason ``draft_validator`` refuses
#: ``attribution.uploaded_by`` outright). An entry naming a person would be exactly the
#: unverifiable claim that refusal exists to prevent, and the operation's own
#: description already promises "WHO recorded it is NOT" stored.
_ATTRIBUTION_CONFIRMATION_QUESTION = (
    "Who contributed to this run, and in what role? Confirmed by whoever sent POST "
    "/api/experiments/{experiment_id}/runs/{run_id}/overrides for block:attribution "
    "with confirmed_by_user: true. This application receives no verified user "
    "identity, so WHO confirmed it is deliberately not recorded."
)


def _attribution_evidence_key(name: str, role: str) -> str:
    """The ``block_evidence`` key ``draft_validator`` looks a contributor up under.

    SPELT ONCE. The validator builds ``f"attribution:{name}|{role}"`` and asks whether
    ``block_evidence`` covers it; a second hand-written copy of that format anywhere is
    a silent coverage failure the moment either side changes.
    """
    return f"attribution:{name}|{role}"


def _attribution_confirmations(payload: object, timestamp: str) -> dict[str, list[dict]]:
    """The ``block_evidence`` entries a confirmed ``block:attribution`` payload earns.

    **THE DEFECT THIS CLOSES, measured over HTTP.** An override at ``block:attribution``
    carrying one contributor was accepted with ``200``, and the export then refused at
    the DRAFT validator with ``official_report: null`` and
    ``attribution.contributors[0]: "contributor has no evidence; attribution must cite
    its source or be user-confirmed"``. The route wrote the block and no
    ``block_evidence``, and ``block:attribution`` is the ONLY write path this build
    offers for a contributor — so a contributor set through the only available route
    could never be exported, by any subsequent request.

    **NO EVIDENCE REQUIREMENT IS WEAKENED, AND THAT IS THE POINT.** The
    ``attribution:<name>|<role>`` coverage rule lives in ``draft_validator`` — a truth-
    plane file under ``CLAUDE.md`` §13 — and is not touched. ``tags`` is exempt from
    coverage BY DESIGN ("authorship IS the confirmation") and attribution deliberately
    is not; that stays true. What changed is that the write now RECORDS the evidence it
    actually has instead of discarding it and then failing a gate for its absence.

    **THE ENTITLEMENT, AND THE COMMITTED PRECEDENT FOR IT.** The claim recorded is "a
    request carrying ``confirmed_by_user: true`` supplied this contributor at this
    operation" — nothing more. That is the SAME basis, on the SAME flag, that
    :func:`_apply_run_field` already mints a ``user_confirmation`` entry on for a run
    field value, using the same ``models.user_confirmation`` helper and therefore the
    same four-key shape ``complete.py`` writes for ``qc:status`` and each
    ``series:<id>``. This is that representation reused, not a second one invented. The
    route refuses the request with ``422 confirmation_required`` before reaching here
    when the flag is absent.

    **ONLY A CONTRIBUTOR THIS APPLICATION CAN KEY, and the rest stay refused.** ``name``
    and ``role`` must both be non-empty ``str``. ``_refuse_override_payload`` applies no
    contributor shape check at all (its docstring records this, measured), so
    ``{"contributors": [{}]}`` and ``{"contributors": [{"name": ["a"], "role": "b"}]}``
    are both stored with ``200``. Minting an entry keyed off a list-valued name would
    let a contributor whose shape the official schema cannot hold pass the coverage gate
    and reach an exported record. So none is minted, the run check and the export gate go
    on refusing those, and the refusal is fail-closed.
    """
    if not isinstance(payload, dict):
        return {}
    contributors = payload.get("contributors")
    if not isinstance(contributors, list):
        return {}
    entries: dict[str, list[dict]] = {}
    for contributor in contributors:
        if not isinstance(contributor, dict):
            continue
        name, role = contributor.get("name"), contributor.get("role")
        if not (isinstance(name, str) and name and isinstance(role, str) and role):
            continue
        entries[_attribution_evidence_key(name, role)] = [
            user_confirmation(
                _ATTRIBUTION_CONFIRMATION_QUESTION, f"{name} | {role}", timestamp
            )
        ]
    return entries


def _rewrite_run_attribution_evidence(run: "ws.Run", entries: dict[str, list[dict]]) -> None:
    """Make the RUN's own ``attribution:`` block evidence exactly ``entries``.

    **REPLACE, NOT MERGE, and the direction matters twice.** An override REPLACES the
    run's whole ``attribution`` block, so a contributor dropped from the payload is gone
    from the record — and leaving their confirmation behind would put a provenance entry
    for a person the record no longer names into ``export.build_sidecar``'s output. It
    would also mean a stale key could cover a contributor re-added later without anyone
    confirming them again. Passing ``{}`` (which the clear operation does) removes them
    all, and ``_merge_block_evidence`` then lets the EXPERIMENT's own entries show
    through again, which is exactly what "this run inherits again" means.

    **THE RUN'S OWN ``block_evidence``, never the experiment's.** The override is the
    run's, so its evidence is the run's; writing to the experiment would attach one
    run's confirmation to every sibling that never received it.

    **IDEMPOTENT BY CONSTRUCTION, which is a requirement here rather than a nicety.**
    The operation's published contract says recording the same override twice is a no-op
    that does not restamp or move the run's revision, and ``save_versioned`` keeps that
    promise by comparing the authoritative signature. An entry carries a timestamp, so
    an unconditional rewrite would break it. An existing entry whose question and answer
    already match is therefore KEPT with its original timestamp, and only a genuinely
    new confirmation is stamped.
    """
    draft = run.draft if isinstance(run.draft, dict) else {}
    run.draft = draft
    existing = draft.get("block_evidence")
    existing = existing if isinstance(existing, dict) else {}

    def _same(kept, fresh) -> bool:
        return (
            isinstance(kept, list)
            and len(kept) == 1
            and isinstance(kept[0], dict)
            and kept[0].get("source_type") == fresh[0]["source_type"]
            and kept[0].get("question") == fresh[0]["question"]
            and kept[0].get("answer") == fresh[0]["answer"]
        )

    rebuilt = {
        key: value
        for key, value in existing.items()
        if not (isinstance(key, str) and key.startswith("attribution:"))
    }
    for key, fresh in entries.items():
        prior = existing.get(key)
        rebuilt[key] = prior if _same(prior, fresh) else fresh
    if rebuilt:
        draft["block_evidence"] = rebuilt
    else:
        draft.pop("block_evidence", None)


@router.post(
    "/experiments/{experiment_id}/runs/{run_id}/overrides",
    tags=[TAG_EXPERIMENTS],
    summary="Override One Inherited Value on a Run",
    description=(
        "Records that ONE run deliberately holds its own value at ONE record-level "
        "address, instead of the value it inherits. Returns the refreshed run and "
        "when the override was recorded.\n\n"
        "Nothing is copied down. The run stores the override and only the override, "
        "so every OTHER record-level value it holds still resolves from the record "
        "and still changes when the record does. The override itself does not: it "
        "keeps the value you gave it, and it keeps a copy of the inherited value it "
        "displaced at the moment it was recorded, which the run view reports as "
        "`displaced_payload` beside the record's current `inherited_payload`. The "
        "two legitimately differ once the record-level value is edited afterwards.\n\n"
        "WHAT IS RECORDED, AND WHAT IS NOT. The time of the override and the value "
        "it displaced are stored. WHO recorded it is NOT: this application receives "
        "no verified user identity, so no name is attached rather than an unverified "
        "one being attached.\n\n"
        "Requires `confirmed_by_user: true` and THE RUN's current `ETag` in "
        "`If-Match` — not the record's. Omitted is `428`, malformed is `400`, and "
        "stale is `412` with nothing written and the run's current `ETag` echoed.\n\n"
        "`address` is spelt exactly as the run's `inherited` map spells it — "
        "`field:<official.dotted.path>`, `block:attribution` or `block:tags`. "
        "Appearing in that map is where a client READS the spelling, and it is "
        "neither necessary nor sufficient: `block:tags` is overridable but is absent "
        "from the map until the record carries a tag, and `field:system.domain` is "
        "reported there but is NOT overridable, because the set of overridable field "
        "paths is the deterministic extractor's own map of official paths and that one "
        "is not in it. A run-level address, a misspelt or invented path, and one the "
        "contract assigns to neither level are each rejected with `422` naming the "
        "address; a run's own fields are edited on the run instead. A "
        "`field:` payload must be a draft field envelope the no-guessing rules "
        "accept — a `verified` value carrying no evidence is refused, not stored — "
        "and a `block:` payload must be the block itself, of the type the official "
        "schema declares for it. Nothing is written on any refusal.\n\n"
        "Recording the same override twice is a no-op: the recorded time is not "
        "restamped and the run's revision does not advance."
    ),
    response_description=(
        "The refreshed run and the override's recorded time, with the run's new "
        "`ETag`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_RUN_NOT_FOUND, **_R_PRECONDITION},
)
def post_run_override(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    run_id: RunId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"confirmed_by_user\": true, \"address\": \"<field:… or block:…>\", "
            "\"payload\": <the envelope or the block>}`. Omitting "
            "`confirmed_by_user: true`, naming an address that is not an inherited "
            "record-level one, or sending a payload of the wrong shape — or one JSON "
            "cannot represent (`NaN`, `Infinity`, a lone surrogate) — is rejected "
            "with `422` and writes nothing."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. THE RUN's current `ETag`, exactly as a run read operation "
            "returned it — not the record's."
        ),
    ),
):
    # THE ADDRESS IS IN THE BODY, NOT THE URL, and that is a decision rather than a
    # convenience. An address is ONE namespaced token — `field:sample.material.name`,
    # `block:tags` — and it is the same token the run view already publishes as the
    # KEY of its `inherited` map. Keeping it in the body means a client sends back
    # exactly what it read, with no splitting, no re-joining and no percent-encoding
    # of the `:` a path segment would need care over. Splitting it into two path
    # segments would have been clean to route and would have put a SECOND spelling of
    # an address on the wire, which is the ambiguity `parse_address`'s namespace
    # prefix exists to remove. Both operations therefore take it the same way, and
    # this API's own convention is action-named POST sub-paths (`/edit`, `/check`,
    # `/validate`, `/answers`) rather than CRUD on a URL-identified resource.
    #
    # Existence pre-check OUTSIDE the lock, as every other mutation does, so a bogus
    # id never pins a permanent entry in the never-evicting lock map.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        run = exp.get_run(run_id)
        if run is None:
            return _run_not_found(experiment_id, run_id)
        if body.get("confirmed_by_user") is not True:
            return _confirmation_required("override an inherited value on a run")
        precondition = _check_if_match(if_match, _RunPrecondition(run, exp.id))
        if precondition is not None:
            return precondition

        resolved = _override_address(body)
        if resolved is None:
            return _not_overridable(body.get("address"))
        address, kind, name = resolved
        refusal = _refuse_override_payload(kind, name, body.get("payload"))
        if refusal is not None:
            return refusal

        # THE DOMAIN'S OWN REFUSALS ARE MAPPED EVEN THOUGH THE GATES ABOVE MAKE THEM
        # UNREACHABLE TODAY, and the point is the day they stop being unreachable.
        # `EXPERIMENT_OVERRIDABLE_ADDRESSES` is derived from the same two classifiers
        # `set_run_override` consults, so the two agree by construction — but they are
        # two expressions of one rule, and if they ever disagree the honest outcome is
        # the typed refusal a client can act on, not an unhandled exception rendered as
        # a 500 with a traceback. `NotOverridable` is a `ValueError`, so the malformed
        # address `parse_address` raises on is caught by the same clause.
        try:
            override = exp.set_run_override(run, address, body.get("payload"))
        except ValueError:
            return _not_overridable(address)

        # THE CONFIRMATION THIS REQUEST EARNED IS RECORDED, not discarded and then
        # missed at the export gate. `confirmed_by_user is not True` was refused above,
        # so by this line a person has said "store this"; for `block:attribution` that
        # is the only thing that can ever satisfy `draft_validator`'s coverage rule for
        # a contributor, and without it a contributor set through the only write path
        # this build offers could never be exported. See `_attribution_confirmations`
        # for the entitlement and for the shapes it deliberately declines to key.
        #
        # IT IS DONE HERE RATHER THAN IN `set_run_override` because the fact being
        # recorded is the ROUTE's: the domain model was not told about the flag and
        # should not have to be, and nothing that reaches the model by another path
        # then mints a confirmation nobody made.
        if address == ws.block_address("attribution"):
            _rewrite_run_attribution_evidence(
                run, _attribution_confirmations(body.get("payload"), _now_iso())
            )

        # The client's validator is the RUN's, so it is deliberately NOT passed to
        # `_save_versioned` — see `patch_run` for why echoing a run version as a
        # record conflict's `expected_version` would be two things wearing one name.
        _changed, stale = _save_versioned(exp, None)
        if stale is not None:
            return stale  # another writer won the race; this override was not recorded
        response.headers["ETag"] = f'"{run.version_token()}"'
        return {
            "run": _run_view(exp, run),
            "override": {"address": address, "recorded_utc": override.recorded_utc},
        }


@router.post(
    "/experiments/{experiment_id}/runs/{run_id}/overrides/clear",
    tags=[TAG_EXPERIMENTS],
    summary="Restore One Inherited Value on a Run",
    description=(
        "Removes ONE run's override at ONE record-level address, so the run "
        "inherits again. Returns the refreshed run and whether an override was "
        "actually there.\n\n"
        "The run goes back to holding NO value at that address — not to holding a "
        "copy of what the record currently says — so it resolves from the record "
        "again and follows every later change to it. The value the override "
        "displaced is not restored onto the run, because it was never taken off "
        "the record in the first place.\n\n"
        "Requires `confirmed_by_user: true` and THE RUN's current `ETag` in "
        "`If-Match` — not the record's. Omitted is `428`, malformed is `400`, and "
        "stale is `412` with nothing written and the run's current `ETag` echoed.\n\n"
        "`address` is spelt exactly as the run's `inherited` map spells it, and the "
        "admissible set is the same one the override operation accepts — appearing in "
        "that map is neither necessary nor sufficient, for the reasons that operation "
        "states. Anything that could not hold an override in the first place is "
        "rejected with `422` naming it, rather than reported as an override that was "
        "not there. Clearing an "
        "address that carries no override IS a success — `cleared` is `false`, "
        "nothing is written, and the run's revision does not advance — so a client "
        "may repeat the request or retry a dropped one safely."
    ),
    response_description=(
        "The refreshed run and whether an override was removed, with the run's "
        "current `ETag`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_RUN_NOT_FOUND, **_R_PRECONDITION},
)
def post_run_override_clear(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    run_id: RunId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"confirmed_by_user\": true, \"address\": \"<field:… or block:…>\"}`. "
            "Omitting `confirmed_by_user: true`, or naming an address that could not "
            "hold an override, is rejected with `422` and writes nothing."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. THE RUN's current `ETag`, exactly as a run read operation "
            "returned it — not the record's."
        ),
    ),
):
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        run = exp.get_run(run_id)
        if run is None:
            return _run_not_found(experiment_id, run_id)
        if body.get("confirmed_by_user") is not True:
            return _confirmation_required("clear an override on a run")
        precondition = _check_if_match(if_match, _RunPrecondition(run, exp.id))
        if precondition is not None:
            return precondition

        resolved = _override_address(body)
        if resolved is None:
            return _not_overridable(body.get("address"))
        address, _kind, _name = resolved
        try:
            cleared = exp.clear_run_override(run, address)
        except ValueError:
            return _not_overridable(address)

        # AND THE CONFIRMATIONS THAT OVERRIDE EARNED GO WITH IT. The run holds no
        # attribution block of its own any more, so a stored confirmation for one of
        # its contributors is provenance for a claim this run no longer makes — it
        # would reach `export.build_sidecar` naming somebody the record does not.
        # `_merge_block_evidence` then lets the EXPERIMENT's own entries show through
        # again, which is what "the run inherits again" has to mean for evidence too.
        # Unconditional, exactly as the save below is: on a clear that removed nothing
        # there is nothing to remove here either, and `save_versioned` still writes
        # nothing because the signature did not move.
        if address == ws.block_address("attribution"):
            _rewrite_run_attribution_evidence(run, {})

        # SAVED UNCONDITIONALLY, INCLUDING THE NO-OP, and the no-op still does not move
        # the run: `save_versioned` persists only when the authoritative signature
        # changed, so a clear that removed nothing writes nothing and leaves `rev`
        # alone. Branching on `cleared` here would add a second path to the same
        # outcome and would skip the durable-conflict check on it.
        _changed, stale = _save_versioned(exp, None)
        if stale is not None:
            return stale  # another writer won the race; this clear was not applied
        response.headers["ETag"] = f'"{run.version_token()}"'
        return {"run": _run_view(exp, run), "cleared": cleared}


@router.post(
    "/experiments/{experiment_id}/runs/{run_id}/answers",
    tags=[TAG_EXPERIMENTS],
    summary="Answer One Run's Blocking Questions",
    description=(
        "Applies caller-supplied answers to ONE RUN's open blocking questions and "
        "returns the refreshed question list for the whole record, its status, the "
        "record's new revision metadata, the derived workflow, and the downstream "
        "invalidation.\n\n"
        "WHY THIS EXISTS SEPARATELY FROM THE RECORD'S OWN `/answers`. A spectrum, a "
        "QC verdict, a descriptor and an asset hash are per-RUN: each run is one "
        "official ISAAC record, and the record's composed draft reads those blocks "
        "off the run. Answering them on the record once runs exist would write a "
        "value no exported record reads, so that route refuses them with `409 "
        "belongs_to_a_run` and names this one.\n\n"
        "`If-Match` is THE RUN's `ETag`, exactly as `GET .../runs/{run_id}` returned "
        "it — not the record's. The two are different validators and the record's "
        "will not match.\n\n"
        "The keys are the same keys the record's `/answers` takes, and come from "
        "`GET /api/experiments/{experiment_id}/pending`, where a run-owned question "
        "carries the `run_id` it belongs to. ~~An UNRECOGNISED key is ignored rather "
        "than invented, exactly as on the record~~ — it is now REFUSED with `422 "
        "unrecognized_field`, exactly as on the record, because dropping it silently "
        "produced a `200` claiming the submitted value was identical to one this run "
        "had never held. **THAT REFUSAL IS NARROWER THAN ~~\"either acted on or "
        "refused by name\"~~, AND THE SCOPE IS STATED RATHER THAN LEFT TO BE "
        "DISCOVERED:** it "
        "fires only where NOTHING in the body is recognised. An unrecognised key "
        "travelling beside a recognised one is still dropped on a `200` that does not "
        "name it \u2014 what that `200` may no longer do is claim the submitted value "
        "was identical, because the reason is withheld entirely whenever anything was "
        "dropped. A `series`, `qc` or `descriptor` value the run cannot hold is "
        "likewise refused with `422 invalid_field_value` rather than declined in "
        "silence. And a recognised key whose question "
        "on THIS run is already CLOSED is refused with `422 already_answered` and "
        "sent to the run's `/edit`, because applying it would write nothing while "
        "reporting a change."
        "\n\n" + _BOUNDED_PENDING_PARAGRAPH
    ),
    response_description=(
        "The record's refreshed blocking questions, status, revision metadata, "
        "workflow and invalidation, with the RECORD's new `ETag`."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_RUN_NOT_FOUND,
        **_R_PRECONDITION,
        # DECLARED, because it was not, and this operation's `422` previously carried
        # only the framework's "Validation Error" — the same gap its sibling `/edit`
        # had, recorded in that route's own `responses` note.
        **_R_ANSWER_REFUSED,
    },
)
def post_run_answers(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    run_id: RunId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"confirmed_by_user\": true, \"answers\": {<key>: <value>}}`. Omitting "
            "`confirmed_by_user: true` is rejected with `422`."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description="Required. THE RUN's current `ETag` — not the record's.",
    ),
):
    return _apply_to_run(
        scope=scope,
        experiment_id=experiment_id,
        run_id=run_id,
        response=response,
        body=body,
        if_match=if_match,
        correcting=False,
    )


@router.post(
    "/experiments/{experiment_id}/runs/{run_id}/edit",
    tags=[TAG_EXPERIMENTS],
    summary="Correct One Run's Already-Answered Field",
    description=(
        "Overwrites a value ONE RUN has already confirmed, recording a fresh user "
        "confirmation beside the previous one rather than replacing it. Same key set "
        "and same refusals as the record's `/edit`; `If-Match` is THE RUN's `ETag`.\n\n"
        "A body that names no editable field is `422` rather than a silent no-op, and "
        "a recognised field carrying a value the store cannot keep is `422` "
        "`invalid_field_value` — the value was the problem, not the field name."
        "\n\n" + _BOUNDED_PENDING_PARAGRAPH
    ),
    response_description=(
        "The record's refreshed questions, status, revision metadata, workflow and "
        "invalidation, with the RECORD's new `ETag`."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_RUN_NOT_FOUND,
        **_R_PRECONDITION,
        # THE SAME FOUR DOMAIN REFUSALS THE RECORD-LEVEL CORRECTION DECLARES, from the
        # same constant. This route's 422 carried only the framework's "Validation
        # Error" while it performed all four, so a machine client reading the contract
        # before calling found `not_yet_answered`, `unrecognized_field` and
        # `invalid_field_value` described nowhere — and `not_yet_answered` is the one
        # whose body a client is expected to ACT on, by following `answer_at`.
        **_R_CORRECTION_REFUSED,
    },
)
def post_run_edit(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    run_id: RunId,
    response: Response,
    body: dict = Body(..., description="`{\"confirmed_by_user\": true, \"answers\": {...}}`."),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description="Required. THE RUN's current `ETag` — not the record's.",
    ),
):
    return _apply_to_run(
        scope=scope,
        experiment_id=experiment_id,
        run_id=run_id,
        response=response,
        body=body,
        if_match=if_match,
        correcting=True,
    )


def _apply_to_run(
    *, scope, experiment_id, run_id, response, body, if_match, correcting: bool
):
    """The shared body of the two run-level write routes.

    ONE FUNCTION, because the two differ only in which core writer they call and in
    what an unusable value means. Two copies of a lock/precondition/save sequence is
    how a precondition ends up enforced on one path and not the other.

    THE LOCK IS PER RECORD, not per run — runs live inside the record's document, so
    two runs of one record serialise against each other, which is exactly what makes
    their independent `If-Match` validators safe. That is the same rule `patch_run`
    states and follows.

    THE PRECONDITION IS THE RUN'S. A run carries its own version token, so a client
    editing run B is not defeated by a concurrent write to run A — and a client
    holding the RECORD's token cannot use it here, which is deliberate: it would let a
    caller write a run it never read.
    """
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)
        run = exp.get_run(run_id)
        if run is None:
            return _run_not_found(experiment_id, run_id)
        if body.get("confirmed_by_user") is not True:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "confirmation_required",
                    "message": (
                        "confirmed_by_user must be true to correct a field."
                        if correcting
                        else "confirmed_by_user must be true to apply answers."
                    ),
                },
            )
        precondition = _check_if_match(if_match, _RunPrecondition(run, exp.id))
        if precondition is not None:
            return precondition

        pre_steps = _workflow_for(exp)["ordered_steps"]
        submitted_fields = [
            k for k, v in (body.get("answers") or {}).items() if v not in (None, "")
        ]
        timestamp = _now_iso()
        run_draft = run.draft if isinstance(run.draft, dict) else {}
        # MATERIALISE A LEGACY RUN'S QUESTIONS BEFORE WRITING. A run created before
        # `_seed_for_new_run` existed has no `pending` key, and `apply_answers` iterates
        # that key and then assigns it back unconditionally — so on such a draft it
        # matched no branch, applied NOTHING, and wrote `[]`. Measured: answering that
        # run's QC verdict returned 200 reporting `pending: []`, stored `qc: None`,
        # erased the derived questions permanently, and left the record claiming nothing
        # was pending while its export refused. A 200 that drops the answer and destroys
        # the question is the worst outcome available.
        #
        # `ws.run_questions` is the SAME derivation `Experiment.pending()` reads, so what
        # a scientist was shown is exactly what is now stored — this makes the derived
        # list durable rather than inventing a second one.
        if "pending" not in run_draft:
            run_draft = {**run_draft, "pending": ws.run_questions(run)}
        apply_shape = _answers_to_apply_shape(
            body.get("answers") or {}, run_draft, timestamp, edit_only=correcting
        )
        # ASKED OF `run_draft` — the draft these two writers are given, including a
        # legacy run's materialised `pending`, so a still-open asset URI counts as
        # recognised on the run that owns it.
        dropped = _dropped_answer_keys(
            body.get("answers") or {}, run_draft, edit_only=correcting
        )
        if not correcting:
            # THE ANSWERING PATH ONLY. The correcting path already has this refusal, as
            # `not _has_correction_target(apply_shape)` a few lines down — which is the
            # rule this one was modelled on rather than a second opinion about it.
            #
            # AHEAD OF THE EDGE REFUSAL, so the two answers operations refuse at the same
            # point in the sequence. It reads the RAW body, so it does not need
            # `apply_shape` and is not weakened by running after the mapper here and
            # before it on the record route.
            refusal = _refuse_a_body_that_names_nothing_answerable(
                body.get("answers") or {},
                dropped,
                {"experiment_id": exp.id, "run_id": run.id},
            )
            if refusal is not None:
                return refusal
        # BEFORE THE BRANCH, because the condition is the same on both sides of it: the
        # answering writer and the correcting writer BOTH write `edge` only into an
        # existing `implicit[]` entry, so a run draft with no such entry produces a 200
        # about a write that could not happen either way. Asked of `run_draft`, which is
        # the draft these two writers are given — including a legacy run's materialised
        # `pending`, which the lines above have already merged in.
        refusal = _refuse_edge_with_nothing_to_confirm(
            run_draft, apply_shape, {"experiment_id": exp.id, "run_id": run.id}
        )
        if refusal is not None:
            return refusal
        if correcting:
            # THE RUN'S OWN QUESTIONS, not the record's. `run_draft` is what
            # `_answers_to_apply_shape` was just given, and it carries the
            # materialised `pending` for this run — so "still open" is asked of the
            # run that owns the value, which is the only level at which the question
            # means anything once a record has runs.
            refusal = _refuse_correcting_an_unanswered_key(
                run_draft,
                body.get("answers") or {},
                # THE RUN'S OWN `/answers`, not the record's. The literal that used to
                # be baked into the refusal named the record's, which on a record that
                # has runs is the one operation guaranteed to refuse these keys — so a
                # compliant client following the refusal was refused a second time and
                # had to follow a second redirect to arrive where this refusal should
                # have sent it in the first place.
                answer_at=_ANSWERS_OPERATION_RUN,
                identifiers={"experiment_id": exp.id, "run_id": run.id},
            )
            if refusal is not None:
                return refusal
            if not _has_correction_target(apply_shape):
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": "unrecognized_field",
                        "message": "No editable field was recognized in the request.",
                    },
                )
            wrong_typed = [
                key
                for key, value in apply_shape.items()
                if key not in ("timestamp", "asset_sha256")
                and not _correction_is_storable(key, value)
            ] + [
                uri
                for uri, sha in (apply_shape.get("asset_sha256") or {}).items()
                if not _correction_is_storable(uri, sha)
            ]
            if wrong_typed:
                # The record route's refusal verbatim — same error, same keys, same
                # deliberate silence about the cause. Two different messages for one
                # condition is how a client ends up branching on prose.
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": "invalid_field_value",
                        "key": wrong_typed[0],
                        "keys": wrong_typed,
                        "message": (
                            "This correction is not a shape the record can store, so "
                            "nothing was written. The stored value is unchanged."
                        ),
                    },
                )
            draft_before = run_draft
            run.draft = apply_corrections(run_draft, apply_shape)
        else:
            # THE SAME SIZE/DEPTH/RENDERABILITY SCREEN THE RECORD's `/answers` APPLIES,
            # from the same function. This branch is the run-level ANSWERING path and it
            # had no value-side screen at all, while the `correcting` branch three lines
            # up has had one since the correction routes were hardened — so a value
            # `/edit` refused with a typed `422` was accepted and written here. Two
            # ingresses for one condition need one screen, or they drift; that is the
            # argument for `_refuse_unstorable_answer` being a function rather than a
            # second inline comprehension.
            #
            # BEFORE `_refuse_answering_an_already_answered_key`, because that refusal is
            # about the QUESTION's state and this one is about whether the value can exist
            # in the store at all. A caller told "already answered" about a value that
            # could never have been stored has been told the less useful of two true
            # things.
            refusal = _refuse_unstorable_answer(apply_shape, body.get("answers") or {})
            if refusal is not None:
                return refusal
            # THE MIRROR OF THE REFUSAL DIRECTLY ABOVE, on the answering side, and asked
            # of `run_draft` for the same reason the correcting branch asks it of
            # `run_draft`: the run owns the value, so "already answered" only means
            # anything at the level that holds it. `run_draft` carries the materialised
            # `pending` for a legacy run, so a run whose questions were derived rather
            # than stored is judged on the same list a scientist was shown.
            refusal = _refuse_answering_an_already_answered_key(
                run_draft,
                body.get("answers") or {},
                timestamp,
                edit_at=_EDIT_OPERATION_RUN,
                identifiers={"experiment_id": exp.id, "run_id": run.id},
            )
            if refusal is not None:
                return refusal
            draft_before = run_draft
            run.draft = apply_answers(run_draft, apply_shape)

        # THE SAME LOG THE RECORD PATH KEEPS, and it was missing. `answer_log` is what
        # `workspace._at_risk_summary` counts to tell an operator how much confirmed work
        # a destructive reset would discard — its docstring says "one entry is appended
        # per submission that actually changed the authoritative draft". Without this, two
        # confirmed RUN answers reported `confirmed_answers: 0`, so the disclosure a
        # scientist reads before a reset under-counted their own work. Measured by an
        # independent review. `run_id` is recorded because the entry is otherwise
        # indistinguishable from a record-level one.
        exp.answer_log.append(
            {("edited" if correcting else "applied"): apply_shape, "run_id": run.id, "at": timestamp}
        )
        changed, stale = _save_versioned(exp, if_match=None)
        if not changed:
            # Byte-stable no-op: discard the speculative append, exactly as the record
            # path does. `answer_log` is excluded from the rev signature, so leaving it
            # would grow the log for a submission that changed nothing.
            exp.answer_log.pop()
        # NO PRAGMA. It read `# pragma: no cover - if_match=None cannot go stale`, and
        # an independent review pointed out that the reasoning is wrong: this branch is
        # reached from `DurableWriteConflict`, which the DATABASE's compare-and-swap
        # predicate raises, entirely independently of `if_match`. It is reachable on the
        # PostgreSQL deployment, and suppressing coverage of it hid that.
        if stale is not None:
            return stale
        # `draft_before` is `run_draft` — the draft the writer was actually handed,
        # INCLUDING a legacy run's materialised `pending`. That is what makes the
        # blocker-resolution half of the test honest: the question a scientist was
        # shown is the question this compares against.
        # WHAT LANDED, NOT WHAT WAS SUBMITTED. `_fields_the_shape_carries` removes keys
        # the core never received; `_fields_the_write_landed` additionally removes keys
        # it received and DECLINED — a wrong-typed `series` reported "Updated 1
        # field(s)" while the stored value was `None`. See that function for the
        # measurement. `Updated 0 field(s)` is now reachable with `changed: true`, on a
        # write whose only effect was materialising a legacy run's derived questions;
        # that sentence is literally true and is left alone rather than replaced with
        # one that would have to guess WHY the document moved.
        changed_fields = (
            _fields_the_write_landed(apply_shape, submitted_fields, draft_before, run.draft)
            if changed
            else []
        )
        invalidation = dependencies.build_invalidation(
            changed=changed,
            changed_fields=changed_fields,
            pre_steps=pre_steps,
            post_exp=exp,
            # THE CALLER'S ANSWER TO "DID YOU COMPARE?" — see
            # `_resubmission_was_identical` for why a fully storable non-empty shape
            # plus `changed=False` IS an identical resubmission, and why an empty one
            # is not. `build_invalidation` names no cause without it.
            #
            # `and not dropped` IS THE OTHER HALF, and it is the half that closes the
            # ride-along case. A body carrying one recognised key beside one unrecognised
            # one still has the unrecognised one dropped in silence; what it must not
            # also get is a sentence saying the submitted value was already stored, which
            # a reader would apply to the key that vanished. When anything was dropped
            # this route claims nothing.
            identical=_resubmission_was_identical(apply_shape) and not dropped,
        )
        # THE WHOLE RECORD's questions, not this run's. A scientist working through a
        # multi-run record needs to know what is left overall, and every entry carries
        # the `run_id` that owns it, so nothing is ambiguous about where each belongs.
        #
        # ~~"the whole record's questions"~~ is now the whole record's questions
        # BOUNDED TO A WINDOW, and the old sentence is struck rather than rewritten
        # because its reasoning is why the window is over the RECORD's list at all
        # rather than over this run's. What is left overall is still reported, as
        # `pending_page.total`, on every response — so the claim the sentence was
        # protecting is served as a number instead of as 3,000 entries. The window is
        # ANCHORED on `run.id`, so this run's own open questions are always in it.
        result = _mutation_pending_response(exp, experiment_id, unit_run_id=run.id)
        result["status"] = exp.status()
        result.update(vc.version_fields(exp))
        result["run_version"] = run.version_token()
        result["workflow"] = _workflow_for(exp)
        result["invalidation"] = invalidation
        response.headers["ETag"] = exp.etag()
        return result


@router.post(
    "/experiments/{experiment_id}/runs/{run_id}/check",
    tags=[TAG_VALIDATION],
    summary="Check One Run",
    description=(
        "Checks the official record ONE run would export — its own content plus "
        "the record-level content it inherits — and returns the no-guessing draft "
        "verdict, the `official` block, and the run's open blocking "
        "questions.\n\n"
        "**The `official` block carries the vendored official ISAAC schema's verdict "
        "WHERE THE OFFICIAL VALIDATOR RAN — and otherwise the findings that stopped "
        "the export before it could.** `official.official_validator_ran` SAYS WHICH, "
        "and it is the field to branch on: `true` means the official validator "
        "examined the document these `errors` describe, `false` means the export was "
        "refused before it was reached — by the no-guessing draft check, or by "
        "ISAAC's own anchored-pattern exactness gate (a value matching a `^...$` "
        "pattern only because Python's `$` also matches before a trailing newline). "
        "Both kinds arrive under the same `errors` key, so `official.ok: false` is "
        "not by itself evidence that the official schema rejected anything — and "
        "`dry_run` does not answer it, because a dry-run PASS does require official "
        "validation while a dry-run FAILURE may never have reached it. "
        "`official_validator_ran: false` is NOT a verdict: it says the vendored "
        "schema did not speak, never that it refused. `official.schema` names the "
        "schema this deployment would validate against and is stamped on every "
        "response. `POST /api/validate/record` reports the two "
        "gates separately (`schema_ok` and `exactness_errors`).\n\n"
        "Read-only: it writes nothing, exports nothing, and does not advance the "
        "run's or the record's revision. `checked_run_version` states which "
        "revision of the run the verdict describes. Every entry in `blockers` "
        "carries a non-empty `message` taken from what that blocking question "
        "already records — no finding text is composed here.\n\n"
        "Both verdicts come from the same deterministic core functions the "
        "command line and the record-level validate operation use; no second "
        "validator exists. `ok` is true only when both pass, and it is computed "
        "from those alone — an advisory warning never turns a pass into a "
        "failure. If the run has already been exported and its written record "
        "cannot be read, no verdict is invented: the official block reports the "
        "single fixed error `Validation could not be completed.`"
    ),
    response_description=(
        "The draft and official verdicts, the run's blocking questions, and the "
        "run revision that was checked. The official verdict carries "
        "`official_validator_ran` — whether the official schema produced the "
        "findings beside it — `dry_run` — false when the run is already exported, in "
        "which case the RECORD ALREADY WRITTEN was validated rather than a "
        "candidate — and `unavailable: true` "
        "when no verdict could be reached at all, which is not the same as the "
        "schema rejecting the document. The three are independent: `dry_run` names "
        "the DOCUMENT, `official_validator_ran` names the SOURCE of the findings, "
        "and `unavailable` says there is no verdict from any gate."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_RUN_NOT_FOUND},
)
def post_run_check(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    run_id: RunId,
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    run = exp.get_run(run_id)
    if run is None:
        return _run_not_found(experiment_id, run_id)

    # The unit is taken from `export_units()` rather than composed here, so this
    # checks the SAME document the export and the record-level validate operation
    # would — including the sibling grouping, which is a fact about the set and
    # cannot be derived from one run alone. `export_units` mutates only the composed
    # dicts it just built; nothing it does reaches stored state.
    unit = next((u for u in exp.export_units() if u.run_id == run.id), None)
    if unit is None:  # pragma: no cover - `run` came from this same experiment
        return _run_not_found(experiment_id, run_id)

    try:
        draft_report = validate_draft(unit.draft)
        draft_verdict = {
            "ok": draft_report.ok,
            "errors": [{"path": w, "message": m} for w, m in draft_report.errors],
            "warnings": [{"path": w, "message": m} for w, m in draft_report.warnings],
        }
    except Exception:
        # Never 500, and never interpolate the exception into the response — the
        # same fail-closed vocabulary the record-level validate operation uses.
        _log.exception("run check draft validation failed run=%s", run.id)
        draft_verdict = {
            "ok": False,
            "errors": [{"path": "$", "message": "Validation could not be completed."}],
            "warnings": [],
        }

    official = _validate_unit(unit)
    official["schema"] = SCHEMA_LABEL
    # EVERY element carries a non-empty `message`, so a client never has to decide
    # which of several optional keys is the one to render. It is DERIVED from what
    # the blocker already says (`_blocker_message`); nothing new is composed, and
    # `serialize.pending_to_list` is left alone because it is the shape the
    # record-level `/pending` and `/answers` operations already publish.
    #
    # THE ENTRIES COME FROM `Experiment.pending()`, NOT FROM `unit.draft["pending"]`,
    # AND THE DIFFERENCE WAS A MEASURED DEFECT ON A LEGACY RUN.
    #
    # `resolved_run_draft` starts from a deep copy of `run.draft` and then layers the
    # EXPERIMENT-LEVEL addresses over it; `pending` is unclassified
    # (`workspace.block_level`), so it is neither inherited nor synthesised. A run
    # created before `_seed_for_new_run` existed has no `pending` key at all — that is
    # the state `ws.run_questions` was made public for, and every such run is still an
    # empty-drafted run in PostgreSQL. `pending_to_list(unit.draft, ...)` read the
    # absent key and got nothing. Measured over HTTP on such a run::
    #
    #     GET  /experiments/{id}/pending        -> series, qc, descriptor   (3)
    #     GET  /experiments/{id}                -> pending_count 3
    #     POST /runs/{run_id}/check             -> blockers []   ok: false
    #                                             official.ok: false
    #
    # An empty `blockers` beside `ok: false` is the shape a client reads as "it fails
    # and nothing is open to fix" — the same class as `GuidedCompletion` rendering
    # "All blockers resolved" on an empty list, which this repository has already had
    # to correct once on the record-level `/answers` response for the same reason.
    #
    # `Experiment.pending()` is the derivation every other surface uses, and it routes
    # a legacy run through `ws.run_questions`, so this operation now agrees with
    # `GET /pending` and with `pending_count` by construction rather than by
    # coincidence. Filtered to THIS run because the response documents "the run's open
    # blocking questions": the record's own non-run-level questions are deliberately
    # NOT promoted here, which keeps the set this operation reports exactly the set it
    # reported before for a seeded run.
    #
    # NO TIER IS CHANGED. `blockers` is the blocking-question list and nothing else;
    # the advisory tier reaches this response through `official`/`draft` warnings and
    # is not merged in. A non-dict entry (a malformed persisted document) is dropped by
    # the `isinstance` guard, which is what `Experiment.pending()` already declines to
    # repair — and previously reached `entry.get` and raised.
    blockers = [
        {**entry, "message": _blocker_message(entry)}
        for entry in serialize.pending_to_list(
            unit.draft,
            ws.load_demo_answers(),
            example_scope=_example_scope(experiment_id),
            entries=[
                entry
                for entry in exp.pending()
                if isinstance(entry, dict) and entry.get("run_id") == run.id
            ],
        )["pending"]
    ]
    return {
        "ok": bool(draft_verdict["ok"] and official["ok"]),
        "draft": draft_verdict,
        "official": official,
        "blockers": blockers,
        "checked_run_version": run.version_token(),
    }


_RUN_REMOVE_DESCRIPTION = (
    "Removes one run from this record and reports what was removed.\n\n"
    "ONLY A RUN THAT KEEPS NO PUBLISHED RECORD CLAIMED. A run that has produced "
    "an official ISAAC record holds a record and an evidence sidecar that this "
    "application never rewrites. Removing the run that names them would leave "
    "them claimed by nothing, and a later export of this record deletes exactly "
    "such a pair — so this operation refuses that run with `409 run_exported` "
    "and writes nothing. The refusal asks BOTH whether the run carries a "
    "`record_id` AND whether an artifact pair is present on disk under its own "
    "id, because an export writes both files before it persists the state and a "
    "refused state save leaves the pair with no `record_id` naming it.\n\n"
    "Every run that has appeared in a submitted revision carries a `record_id` — "
    "a submission materialises every unit before it records anything — so a "
    "SUBMITTED record is out of this operation's reach. That is a statement "
    "about submitted records specifically, not a claim that removal is the only "
    "way a record can stop being claimed. No revision, submission or official "
    "record is deleted, rewritten or marked by this operation in any case.\n\n"
    "WHAT IS REMOVED is the run's own draft content: the run-level values it "
    "holds, the overrides it recorded, its association with any asset reference, "
    "and its open questions. The record's own values are unchanged, no other run "
    "is changed, the record's asset library keeps every entry, and no file at an "
    "asset `uri` is read or altered — this application has never read one.\n\n"
    "THE REMAINING RUNS KEEP THEIR NUMBERS. Ordinals are not renumbered, so a "
    "record whose runs were 1, 2 and 3 reads 1 and 3 after the second is removed, "
    "and every surviving run's revision and `ETag` are untouched by this request. "
    "`ordinals_compacted` is `false` in the response so a client never has to "
    "infer it. A run added afterwards takes the next number above the highest "
    "still present.\n\n"
    "Removing a run rewrites the record, so this requires `confirmed_by_user: "
    "true` and the RECORD's current `ETag` in `If-Match` — omitted is `428`, "
    "malformed is `400`, and stale is `412` with nothing removed. Repeating the "
    "request for a run that is already gone is `404` rather than a second "
    "success: this operation is addressed to a run, and every other run operation "
    "answers `404` for an id this record does not hold."
)


@router.post(
    "/experiments/{experiment_id}/runs/{run_id}/remove",
    tags=[TAG_EXPERIMENTS],
    summary="Remove a Run from a Record",
    description=_RUN_REMOVE_DESCRIPTION,
    response_description=(
        "What was removed — the run's id, label and number, and the asset "
        "references that went with it — together with how many runs remain, "
        "whether the remaining numbers were changed, and the record's new "
        "revision, with the record's new `ETag`."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_RUN_NOT_FOUND,
        **_R_RUN_EXPORTED,
        **_R_PRECONDITION,
    },
)
def post_run_remove(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    run_id: RunId,
    response: Response,
    body: dict = Body(
        ...,
        description="`{\"confirmed_by_user\": true}`. Nothing else is read.",
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The RECORD's current `ETag`, exactly as a read operation "
            "returned it — not the run's. A run lives inside the record's "
            "document, so removing one rewrites the record."
        ),
    ),
):
    """Remove one run. THE ORDER OF THE FIVE REFUSALS IS THE CONTRACT.

    It is `post_asset_remove`'s order, deliberately, because the two are the same
    shape of act: exists -> confirmed -> domain refusal -> precondition -> write.

    THE PRECONDITION IS CHECKED INSIDE THE SAME CRITICAL SECTION AS THE MUTATION,
    and this repository has a written history of that exact defect on the reset
    path, so it is worth stating rather than assuming. Both `_check_if_match` and
    the removal happen under one `record_lock`, over an experiment re-read INSIDE
    that lock — the copy read by the existence pre-check above is never mutated.
    The durable compare-and-swap in the repository is the second half of it, for
    the writers this process cannot lock against, and `_save_versioned` renders
    its refusal as the same 412 with nothing removed.

    IDEMPOTENCY IS 404, NOT A SECOND 200, and that is a decision. A retry whose
    first attempt succeeded is the case that matters: the record moved, so the
    token it carries is stale — but the run is gone, and the 404 is checked first,
    so the retry is told the truth about the run rather than being sent to
    re-read a version in order to remove something that no longer exists. A 200
    would additionally require this operation to claim a run "was removed" for an
    id that may never have existed on this record, which no other run operation
    does and which is indistinguishable from a mistyped id.
    """
    # Existence pre-check OUTSIDE the lock, exactly as every other mutation does
    # it, so a bogus id never pins a permanent entry in the never-evicting lock map.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        run = exp.get_run(run_id)
        if run is None:
            return _run_not_found(experiment_id, run_id)
        if not isinstance(body, dict) or body.get("confirmed_by_user") is not True:
            return _confirmation_required("remove a run")
        published = _run_published_stem(exp, run)
        if published is not None:
            return _run_exported(experiment_id, run, stem=published)
        precondition = _check_if_match(if_match, exp)
        if precondition is not None:
            return precondition
        # READ BEFORE THE REMOVAL, because after it the run is not reachable from
        # the experiment and the response would have nothing to name. NAMED, NOT
        # COUNTED, for the reason `post_asset_remove` names its runs: a scientist
        # told only "removed" cannot tell which files this measurement stopped
        # citing. The library entries themselves are NOT removed — an asset may be
        # cited by other runs, and by the record itself.
        dropped_assets = [item["asset_id"] for item in assets.run_assets(run)]
        removed_label, removed_ordinal = run.label, run.ordinal
        removed = exp.remove_run(run_id)
        assert removed is not None  # `get_run` above already resolved it under the lock
        _changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another writer won the race; this run was not removed
        # `_changed` is structurally always True here — `_authoritative_signature`
        # covers `runs`, so dropping one cannot leave the signature equal — so it is
        # not branched on, exactly as `post_run` does not branch on it for a create.
        response.headers["ETag"] = exp.etag()
        return {
            "removed_run_id": run_id,
            "removed_run_label": removed_label,
            "removed_run_ordinal": removed_ordinal,
            "asset_references_dropped": dropped_assets,
            "remaining_run_count": len(exp.runs),
            # STATED, NOT INFERRED. The decision and its four reasons live on
            # `Experiment.remove_run`; this is the wire half of it, so a client can
            # tell the difference between "they were not renumbered" and "this
            # build forgot to say".
            "ordinals_compacted": False,
            "experiment_version": exp.version_token(),
        }


# --- 7b. unmapped notes -------------------------------------------------------
#
# WHAT THESE FOUR OPERATIONS ARE FOR. A scientist captures things that no rule can
# place: a sentence about why a scan was repeated, a column heading nothing
# recognises, an aside in a transcript. Today every pipeline in this repository
# still drops such content, silently — NOTHING WAS REWIRED TO FEED THESE
# OPERATIONS. They are the destination that now exists, and the only producer is a
# person typing into the panel: `POST .../notes` has exactly one caller in the
# application, the capture box, which always sends `source: "typed_note"` with no
# run and no candidate. The intended FIRST automatic producer is
# `providers/extraction.py`'s `unrecognised_labels`, which is computed and then
# discarded; wiring it is a later slice, and until it lands no `csv_column`,
# `transcript`, `file_listing_line` or `extraction_residue` note is ever created,
# no note carries a `run_id`, and no note carries a `candidate_field_path`. The
# governing rule for what DOES arrive here is that NOTHING CAPTURED IS EVER
# SILENTLY DISCARDED — there is no DELETE here, and there will not be one.
# Dismissal is a state.
#
# WHAT THEY ARE NOT. None of them writes a scientific value, mints evidence, or
# confirms anything. `isaac_api.notes.Note` cannot even REPRESENT a confirmed value
# — `status`, `verified`, `is_evidence` and `is_field_value` are read-only
# constants on a frozen, slotted dataclass, and those constants are serialised on
# the wire so the guarantee survives the boundary. `src/isaac_records/` and
# `schema/` are untouched by this feature, and no export path reads a note:
# `export_draft` reads `Experiment.draft`, and notes are not in it.
#
# ONE VALIDATOR, THE RECORD'S. Notes live inside the experiment's state document,
# so every write here rewrites the experiment and therefore takes the RECORD's
# `If-Match` — never a run's, and there is deliberately no per-note validator. A
# second concurrency scheme with no consumer is a trap, and `patch_run`'s own
# description already records how easily two tokens for two things get confused.


#: THE COMPLETE SET OF FIELD PATHS A NOTE MAY BE MAPPED TO OR PROPOSED FOR.
#:
#: **A SUBSET OF THE OFFICIAL SCHEMA'S PATHS, NOT ALL OF THEM, AND NO SURFACE MAY
#: SAY OTHERWISE.** It is derived from :data:`EXTRACTOR_FIELD_MAP` — the paths this
#: build's extractor knows how to place — exactly as :data:`RUN_WRITABLE_FIELD_PATHS`
#: is, so the enforced set has ONE definition rather than a second copy free to
#: drift. That derivation is a fact about THIS APPLICATION, and it currently yields
#: 25 paths. The official schema defines many more that are absent from it:
#: `sample.sample_id`, `measurement.qc`, `measurement.series`,
#: `measurement.processing`, `attribution.uploaded_by`, `descriptors`, `links`,
#: `tags` and `assets` are all real. CLAUDE.md §1 makes the official schema not
#: ours to speak for, so a refusal from this set must describe what THIS BUILD can
#: map a note to and must never report the path as one the schema does not define.
#: Widening the set is a product decision about which paths are safe targets, and
#: it is deliberately not made here.
#:
#: Unlike :data:`RUN_WRITABLE_FIELD_PATHS` it is NOT filtered by level: a note is
#: prose about the experiment or about one of its runs, and a scientist saying "this
#: belongs at `sample.material.formula`" is naming a target, not writing a run-level
#: value. The level split governs where a VALUE may be written, and this operation
#: writes none.
#:
#: THE GATE IS MEMBERSHIP, NOT SHAPE, and that is the lesson `patch_run` already
#: paid for: a prefix test admits `sample.material.typo`, which nothing downstream
#: could place. A path outside this set is refused with a typed 422 and is never
#: stored — storing one would let a note point at a target this build cannot resolve,
#: which is a guess with a plausible shape, and plausible shapes get believed.
NOTE_MAPPABLE_FIELD_PATHS: frozenset[str] = frozenset(
    path for path, _coercer in EXTRACTOR_FIELD_MAP.values()
)


#: THE MAPPABLE PATHS SOME WRITE OPERATION IN THIS BUILD WILL ACCEPT A VALUE AT.
#:
#: **IT EXISTS BECAUSE A COPY CLAIM WAS FALSE FOR 7 OF THE 25.** After mapping a note,
#: ``UnmappedNotesPanel`` told the scientist *"It does not write a value — a value
#: still has to be entered and confirmed on the field itself"*, and this operation's
#: description and the ``review`` operation's said the same thing in prose. The first
#: half is true of all 25. The second half describes an ACTION, and for seven of them
#: no request can perform it. Measured over HTTP on a record created through ``POST
#: /api/experiments``, with one run, against every write route this application has —
#: ``POST .../answers``, ``POST .../edit``, ``POST .../runs/{id}/answers``, ``PATCH
#: .../runs/{id}`` and ``POST .../runs/{id}/overrides`` — the six
#: ``system.configuration.*`` paths and ``timestamps.created_utc`` are refused by ALL
#: FIVE (``422 unrecognized_field`` from the four field routes, ``422
#: not_overridable`` from the override route). The sentence pointed at a locked door,
#: on the one screen whose purpose is to stop captured content being thrown away.
#:
#: WHY THOSE SEVEN ARE NOT SIMPLY GIVEN A WRITE ROUTE, which would be the better fix
#: if it were this slice's to make. ``system.configuration`` is a DESIGNATED OPEN
#: namespace in the vendored schema (it declares no ``properties``), ``field_level``
#: deliberately leaves it unclassified, and ``CLAUDE.md`` §15 records the six
#: ``system.configuration.*`` fields as ``unclassified, verified`` pending an external
#: answer — so classifying them here would be deciding an open question rather than
#: reporting a fact. ``timestamps.created_utc`` is likewise unclassified. Widening
#: either is a product decision and is deliberately not made here.
#:
#: DERIVED FROM THE TWO SETS THAT ENFORCE IT, never listed by hand — the discipline
#: its inputs already keep. :data:`RUN_WRITABLE_FIELD_PATHS` is exactly what ``PATCH
#: .../runs/{run_id}`` accepts; :data:`EXPERIMENT_OVERRIDABLE_ADDRESSES` is exactly
#: what ``POST .../runs/{run_id}/overrides`` accepts. A path leaving either set leaves
#: this one, in the same import, so the served answer and the enforced answer cannot
#: drift. ``test_note_value_writability_is_measured_not_asserted`` re-derives it the
#: only way that actually proves it: by sending a write at every one of the 25 paths
#: to every one of the five routes and comparing the observed statuses to this set.
#:
#: TWO THINGS IT DOES NOT PROMISE, and both matter to the copy built on it. It does
#: not promise the value will be ACCEPTED — a closed enum, a required sibling
#: property or the no-guessing rules may still refuse the particular value. And every
#: one of these routes is a RUN's, so a record with no runs yet can write none of
#: them; membership means "a route exists", not "you can do it right now".
NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT: frozenset[str] = frozenset(
    path
    for path in NOTE_MAPPABLE_FIELD_PATHS
    if path in RUN_WRITABLE_FIELD_PATHS
    or ws.field_address(path) in EXPERIMENT_OVERRIDABLE_ADDRESSES
)


#: The largest one note's text may serialise to. A REFUSAL, NEVER A TRUNCATION.
#:
#: "Never truncated" is a promise about what is STORED, and it is kept by refusing
#: an over-large capture outright rather than by silently keeping a prefix — a
#: truncated note is a note that lies about what was written. 256 KiB is four times
#: the run-field limit (:data:`_MAX_VALUE_BYTES`, 64 KiB) because a pasted log
#: excerpt or a block of instrument output is legitimately long prose where a
#: run-level scalar is not, and half the `POST /validate/record` body limit, so it
#: sits inside the two bounds this repository already enforces rather than
#: introducing a new kind of number.
_MAX_NOTE_BYTES = 256 * 1024


#: The path parameter naming a note. One description, so the wording cannot drift.
NoteId = Annotated[
    str,
    Path(
        description=(
            "The id of a note on this experiment, as returned by "
            "`GET /api/experiments/{experiment_id}/notes`."
        )
    ),
]

_R_NOTE_NOT_FOUND: dict = {
    404: {
        "description": (
            "No experiment in the selected workspace has that id, that experiment "
            "holds no note with that id, or the `X-Isaac-Tutorial-Session` header "
            "named a worked-example session that does not exist. A DISMISSED note "
            "is not one of these cases — dismissal is a state, so a dismissed note "
            "is still returned by this operation."
        )
    },
}

#: The body keys each write accepts. Anything else is REFUSED rather than ignored.
#:
#: This is the same defence `FieldCandidate`'s `FORBIDDEN_PROVENANCE_KEYS` provides
#: from the other direction, and it is why the list is a closed allowlist rather
#: than a ban list: a client that sends `{"verified": true}` or `{"status":
#: "verified"}` alongside its note gets a 422 naming the key, instead of a 201 whose
#: body reports `verified: false` while the caller believes otherwise. A note cannot
#: be asked to be a value, not merely refused when it tries.
_NOTE_CAPTURE_KEYS = frozenset(
    {"text", "source", "run_id", "candidate_field_path", "candidate_rule"}
)
_NOTE_REVIEW_KEYS = frozenset(
    {"action", "confirmed_by_user", "field_path", "text", "reason"}
)


def _note_not_found(experiment_id: str, note_id: str) -> JSONResponse:
    """A note this experiment does not hold. Distinct from `_not_found`.

    The two 404s are deliberately different bodies, for the reason
    :func:`_run_not_found` gives: ``experiment_not_found`` means the workspace has
    no such record, ``note_not_found`` means the record was read successfully and
    holds no note under that id. Collapsing them sends a client looking in the
    wrong place.
    """
    return JSONResponse(
        status_code=404,
        content={
            "error": "note_not_found",
            "experiment_id": experiment_id,
            "id": note_id,
        },
    )


def _note_refusal(error: str, message: str, **extra) -> JSONResponse:
    """One typed 422. Every refusal on these routes is one of these."""
    return JSONResponse(
        status_code=422, content={"error": error, "message": message, **extra}
    )


def _unknown_note_keys(body: dict, allowed: frozenset[str]) -> JSONResponse | None:
    """Refuse a body key this operation does not accept. See :data:`_NOTE_CAPTURE_KEYS`."""
    refused = sorted(str(key) for key in body if key not in allowed)
    if not refused:
        return None
    return _note_refusal(
        "unrecognized_field",
        (
            "These keys are not part of this request. Nothing was written. A note "
            "records what was captured and the review acts performed on it; it "
            "carries no status, no verification and no evidence, so a key naming "
            "one of those is refused rather than accepted and ignored."
        ),
        key=refused[0],
        keys=refused,
    )


def _note_text_refusal(raw: object, *, what: str) -> JSONResponse | None:
    """Refuse text that is not text, is blank, or could not be stored intact."""
    if not isinstance(raw, str) or not raw.strip():
        return _note_refusal(
            "invalid_note_text",
            (
                f"{what} must be a non-blank string. A note with no content records "
                "nothing, and a blank one would sit in the review queue as an empty "
                "row nobody can act on."
            ),
        )
    if not _is_storable_value(raw, max_bytes=_MAX_NOTE_BYTES):
        return _note_refusal(
            "unrepresentable_value",
            (
                "This text could not be stored intact — either it is larger than one "
                "note may be, or it contains characters JSON cannot represent (a lone "
                "surrogate), so a record containing it could not be read back. It is "
                "REFUSED rather than shortened: a truncated note misrepresents what "
                "was written. Nothing was written."
            ),
        )
    return None


def _note_view(note: "notes.Note") -> dict:
    """One note, as this API presents it.

    ``to_state()`` is the whole shape, constants included — see its docstring for
    why ``status`` / ``verified`` / ``is_evidence`` / ``is_field_value`` are
    serialised rather than left as a class invariant a JSON reader cannot see.

    ``display_text`` is added here and is a CONVENIENCE, never a replacement: the
    verbatim ``text`` and any ``revised_text`` are both always present, so a client
    that wants to show the original always can, and a client that renders
    ``display_text`` is not quietly hiding that an edit happened.
    """
    return {**note.to_state(), "display_text": note.display_text}


def _notes_payload(exp: Experiment, *, selected: list["notes.Note"]) -> dict:
    """The list body. ``total`` counts what EXISTS, never what was returned."""
    by_state = {state: 0 for state in sorted(notes.NOTE_STATES)}
    for note in exp.notes:
        by_state[note.state] = by_state.get(note.state, 0) + 1
    return {
        "notes": [_note_view(note) for note in selected],
        # THE THREE NUMBERS A FILTERED LIST CANNOT BE HONEST WITHOUT, and the same
        # rule `GET .../runs` follows: `total` is how many notes this record holds,
        # NOT how many were returned, so a client filtering to `unreviewed` still
        # states the record's true size rather than implying the rest are gone.
        "total": len(exp.notes),
        "returned": len(selected),
        "by_state": by_state,
        # A DISCLOSURE OF WHAT THIS BUILD CANNOT PRESENT AS A NOTE. Two kinds, and
        # the single number does not separate them: an entry `Note.from_state`
        # refused, and an entry whose id another note already holds — the second is
        # readable, it just cannot share one id (`workspace._hydrate_notes`). Both
        # are kept in the stored document verbatim and written back out on every
        # save; both are counted here rather than rendered, because this server can
        # neither say what a refused entry contains without inventing it nor say
        # which of two entries an id names. Reporting zero when there are some would
        # be the silent discard this feature exists to end.
        "unreadable_entries": len(exp.unreadable_notes),
        # THE SERVER'S OWN ANSWER TO "WHERE MAY I MAP THIS?", for the reason
        # `_run_view`'s `overridable` flag exists: the alternative is transcribing a
        # classification into the frontend bundle, where it is free to drift from the
        # set the route actually enforces. These are one expression, so the control a
        # client offers and the request the server accepts cannot disagree.
        "mappable_field_paths": sorted(NOTE_MAPPABLE_FIELD_PATHS),
        # AND THE SERVER'S OWN ANSWER TO "AND MAY I THEN ENTER ITS VALUE?", which is a
        # DIFFERENT question and has a different answer for 7 of the 25. Served for
        # exactly the reason the line above is: the panel tells a person what to do
        # next after mapping, and the only alternative to being told is transcribing
        # the two write routes' admissible sets into the frontend, where they are free
        # to drift from what the routes enforce. See
        # `NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT` for the measurement.
        "value_writable_field_paths": sorted(NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT),
        "sources": sorted(notes.NOTE_SOURCES),
        "experiment_version": exp.version_token(),
    }


_NOTE_LIST_DESC = (
    "Return only notes in this review state. Omit it to return every note, "
    "which is the default and includes dismissed ones."
)


@router.get(
    "/experiments/{experiment_id}/notes",
    tags=[TAG_EXPERIMENTS],
    summary="List a Record's Unmapped Notes",
    description=(
        "Lists the content captured against this record that has no confident "
        "schema home — a remark, an unrecognised column heading, an aside in a "
        "transcript — each with what produced it, the run it belongs to when that "
        "is known, its verbatim text, and its review state. Read-only.\n\n"
        "DISMISSED NOTES ARE INCLUDED. Dismissing is a review state reached by an "
        "explicit act and recorded in the note's history; it is not a deletion, "
        "and this API has no operation that deletes a note. `state` narrows the "
        "list on the server and `total` remains how many notes EXIST, so a client "
        "filtering to one state can always say how much of the record it is "
        "showing.\n\n"
        "A note is never a field value. Every note carries `verified: false`, "
        "`is_evidence: false`, `is_field_value: false` and a `status` of "
        "`unmapped_note`, which is deliberately not one of the draft field "
        "statuses — these are constants of the shape, not fields a request can "
        "set. `candidate_field_path` is present only when something deterministic "
        "proposed it and stated the rule it applied; when nothing did, the field "
        "is null rather than a plausible-looking guess.\n\n"
        "`mappable_field_paths` is the server's own list of the field paths a "
        "note may be mapped to. It is a SUBSET of the official schema's field "
        "paths — the ones this build knows how to place — so a target absent "
        "from it may still be a real schema field, and a refusal against this "
        "list says what this application can map a note to rather than what the "
        "official schema defines.\n\n"
        "`value_writable_field_paths` is the SUBSET of those paths that some "
        "write operation in this build accepts a value at — `PATCH "
        "/api/experiments/{experiment_id}/runs/{run_id}` for a run's own field, "
        "`POST /api/experiments/{experiment_id}/runs/{run_id}/overrides` for a "
        "record-level one. MAPPING A NOTE AND ENTERING ITS VALUE ARE DIFFERENT "
        "ACTS, and for 7 of the 25 mappable paths the second one has no route at "
        "all: every write operation refuses them. Mapping to such a path is still "
        "correct and still keeps the content on the record in full — this key "
        "says only that no request can then put a value there, so a client must "
        "not tell a person to go and do it. It promises nothing about a value "
        "being ACCEPTED: a closed enum, a required sibling property or the "
        "no-guessing rules may still refuse the particular value. Both routes are "
        "a run's, so a record with no runs can write none of them yet.\n\n"
        "`unreadable_entries` counts stored entries this build cannot present as "
        "notes. There are two kinds and the count does not separate them: an "
        "entry the note model refused, and an entry whose id another note already "
        "holds — a duplicate is perfectly readable, but two notes cannot answer "
        "to one id. Either way the entry is preserved in the record untouched and "
        "is counted rather than rendered: for a refused entry this server cannot "
        "say what it contains without inventing it, and for a duplicate it cannot "
        "say which entry the id names."
    ),
    response_description=(
        "The record's notes in capture order, the per-state counts, the field "
        "paths a note may be mapped to, and the record's current `ETag`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_TUTORIAL_SCOPE},
)
def list_notes(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    state: Annotated[
        Literal["unreviewed", "mapped", "kept", "dismissed"] | None,
        Query(description=_NOTE_LIST_DESC),
    ] = None,
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    response.headers["ETag"] = exp.etag()
    ordered = exp.sorted_notes()
    selected = [n for n in ordered if state is None or n.state == state]
    return _notes_payload(exp, selected=selected)


@router.post(
    "/experiments/{experiment_id}/notes",
    tags=[TAG_EXPERIMENTS],
    status_code=201,
    summary="Capture an Unmapped Note",
    description=(
        "Stores one piece of captured content that has no confident schema home, "
        "verbatim, and returns it with the record's new revision.\n\n"
        "Capturing a note rewrites the record, so this requires the RECORD's "
        "current `ETag` in `If-Match` — omitted is `428`, malformed is `400`, and "
        "stale is `412` with nothing written. `text` is stored exactly as sent: it "
        "is not trimmed, normalised or shortened, and text too large to store is "
        "REFUSED with `422` rather than truncated, because a shortened note "
        "misrepresents what was written.\n\n"
        "`source` must be one of the values `GET .../notes` reports under "
        "`sources`, and there is no default — a producer that cannot say what "
        "produced its own output is not described by inventing a label for it. "
        "These are this feature's own vocabulary and are deliberately not ISAAC "
        "evidence source types, because a note is not evidence.\n\n"
        "`run_id`, `candidate_field_path` and `candidate_rule` are optional and "
        "nothing supplies them on a caller's behalf. An omitted `run_id` means the "
        "note belongs to the record rather than to a run, and it is never filled "
        "in from the only run that happens to exist. A `candidate_field_path` must "
        "be one of the paths `GET .../notes` reports under `mappable_field_paths` "
        "— a subset of the official schema's paths, not the whole of it — AND must "
        "arrive with the `candidate_rule` that produced it — an unexplained "
        "proposal is a guess, and either half without the other is `422`. Absent "
        "is absent: an empty string is refused, not stored.\n\n"
        "Any other body key is refused with `422` naming it. A note carries no "
        "status, no verification and no evidence, so a request that tries to set "
        "one is rejected rather than accepted and quietly ignored."
    ),
    response_description=(
        "The stored note and the record's new revision, with the record's new "
        "`ETag`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_TUTORIAL_SCOPE, **_R_PRECONDITION},
)
def post_note(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"text\": \"<verbatim content>\", \"source\": \"<one of the "
            "reported sources>\", \"run_id\": \"<optional>\", "
            "\"candidate_field_path\": \"<optional>\", \"candidate_rule\": "
            "\"<required with a candidate path>\"}`. Any other key is refused with "
            "`422`."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The RECORD's current `ETag`, exactly as a read operation "
            "returned it. Notes have no separate validator of their own."
        ),
    ),
):
    # Existence pre-check OUTSIDE the lock, exactly as every other mutation does it,
    # so a bogus id never pins a permanent entry in the never-evicting lock map.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        if not isinstance(body, dict):
            return _note_refusal(
                "invalid_body", "The request body must be a JSON object."
            )
        refused = _unknown_note_keys(body, _NOTE_CAPTURE_KEYS)
        if refused is not None:
            return refused
        # EVERY INPUT IS RESOLVED BEFORE THE PRECONDITION IS EVEN CHECKED, so a
        # malformed request is a 422 whether or not the caller's `If-Match` happens
        # to be current — the same ordering `post_run` uses for its label.
        text_refusal = _note_text_refusal(body.get("text"), what="text")
        if text_refusal is not None:
            return text_refusal
        source = body.get("source")
        if source not in notes.NOTE_SOURCES:
            return _note_refusal(
                "unknown_note_source",
                (
                    "`source` must name what produced this content, and must be one "
                    "of the values this API reports under `sources`. There is no "
                    "default and nothing is guessed from the text."
                ),
                source=source if isinstance(source, str) else None,
                allowed=sorted(notes.NOTE_SOURCES),
            )
        run_id = body.get("run_id")
        if run_id is not None:
            # A NOTE MAY NOT NAME A RUN THIS RECORD DOES NOT HAVE. It is a `422` and
            # not a `404`: the request is to create a note, the record exists, and
            # the thing that is wrong is one field of the body.
            if not isinstance(run_id, str) or exp.get_run(run_id) is None:
                return _note_refusal(
                    "unknown_run",
                    (
                        "This record has no run with that id, so a note cannot be "
                        "attached to it. Omit `run_id` to capture the note against "
                        "the record itself — it is never inferred."
                    ),
                    run_id=run_id if isinstance(run_id, str) else None,
                )
        candidate = body.get("candidate_field_path")
        if candidate is not None and (
            not isinstance(candidate, str) or candidate not in NOTE_MAPPABLE_FIELD_PATHS
        ):
            return _note_refusal(
                "unrecognized_field",
                (
                    "`candidate_field_path` must be one of the paths this build can "
                    "map a note to — the list `GET .../notes` reports under "
                    "`mappable_field_paths`. That list is a SUBSET of the official "
                    "schema's field paths, so this refusal says the path is not one "
                    "this application can propose a note against; it does NOT say "
                    "the official schema has no such field. An invented or misspelt "
                    "path is refused rather than stored: a note pointing at a "
                    "target this build cannot resolve is a guess with a plausible "
                    "shape. Nothing was written."
                ),
                key=candidate if isinstance(candidate, str) else None,
            )
        precondition = _check_if_match(if_match, exp)
        if precondition is not None:
            return precondition
        try:
            note = exp.capture_note(
                text=body["text"],
                source=source,
                run_id=run_id,
                candidate_field_path=candidate,
                candidate_rule=body.get("candidate_rule"),
            )
        except notes.UnsupportedNote as refusal:
            # THE MODEL'S OWN REFUSALS REACH THE CLIENT AS A TYPED 422, NEVER A 500.
            # The checks above cover every shape a UI can send; this covers the ones
            # only the model knows — a candidate rule with no path, a blank optional
            # sent as `""` — so a malformed payload can never escape as a traceback.
            return _note_refusal("unsupported_note", str(refusal))
        _changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another writer won the race; this note was not captured
        # `_changed` is structurally always True here: a new note with a fresh id
        # cannot leave the authoritative signature equal.
        response.headers["ETag"] = exp.etag()
        return {"note": _note_view(note), "experiment_version": exp.version_token()}


@router.get(
    "/experiments/{experiment_id}/notes/{note_id}",
    tags=[TAG_EXPERIMENTS],
    summary="Read One Unmapped Note",
    description=(
        "Returns one note: its verbatim text, any revised wording, what produced "
        "it, the run it belongs to when that is known, its review state, and the "
        "full history of the acts performed on it. Read-only.\n\n"
        "A DISMISSED NOTE IS RETURNED NORMALLY. Dismissal is a state, not a "
        "deletion, and the history records when it happened and what it was "
        "dismissed from. The verbatim capture is returned even when the note has "
        "been edited — an edit stores the corrected wording beside the original "
        "and never replaces it, and each superseded wording is kept on the history "
        "entry that replaced it.\n\n"
        "The `ETag` header carries THE RECORD's current revision, which is what "
        "capturing or reviewing a note requires in `If-Match`. Notes have no "
        "separate validator of their own, because a note is stored inside the "
        "record's own document."
    ),
    response_description="The note, with the record's current `ETag`.",
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_NOTE_NOT_FOUND},
)
def get_note(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    note_id: NoteId,
    response: Response,
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    note = exp.get_note(note_id)
    if note is None:
        return _note_not_found(experiment_id, note_id)
    response.headers["ETag"] = exp.etag()
    return {"note": _note_view(note)}


@router.post(
    "/experiments/{experiment_id}/notes/{note_id}/review",
    tags=[TAG_EXPERIMENTS],
    summary="Review One Unmapped Note",
    description=(
        "Performs one of the four review acts on a note — `map`, `edit`, `keep` or "
        "`dismiss` — and returns the note as it now stands. Each act is appended "
        "to the note's history with the state it moved from and the time it "
        "happened; nothing is ever removed.\n\n"
        "Requires `confirmed_by_user: true` and the RECORD's current `ETag` in "
        "`If-Match` — omitted is `428`, malformed is `400`, and stale is `412` "
        "with nothing written. Re-performing an act that changes nothing is a "
        "no-op: it writes nothing, adds no history entry and does not advance the "
        "record's revision.\n\n"
        "`map` records the official field path a scientist says this note belongs "
        "to, and requires `field_path` to be one of the paths `GET .../notes` "
        "reports under `mappable_field_paths`. IT WRITES NO VALUE. Deriving a "
        "value from prose would mean deciding what the value is, which this "
        "application makes a person do through a separate confirmed write; a "
        "mapped note says where the content belongs, not what the field should "
        "hold. WHETHER SUCH A WRITE EXISTS FOR THE MAPPED PATH IS A SEPARATE "
        "QUESTION, and for 7 of the 25 mappable paths the answer is no — `GET "
        ".../notes` reports `value_writable_field_paths`, the subset some write "
        "operation accepts a value at. Mapping outside it is still a correct and "
        "useful act and the content stays on the record in full, but no request "
        "in this build can then put a value there, and nothing here implies one "
        "can.\n\n"
        "`edit` stores a corrected wording BESIDE the verbatim capture and never "
        "replaces it, and leaves the review state alone — fixing a typo is not a "
        "triage decision. `keep` records that this content is prose about the "
        "experiment and belongs to no field, which is a first-class outcome and "
        "not an unfinished review. `dismiss` sets the note aside and is the "
        "closest thing to a delete this API offers, which is to say it is not one: "
        "the note remains listed, readable and unchanged, and an optional `reason` "
        "is stored when given and left absent when not, because a justification "
        "nobody wrote is not invented on their behalf.\n\n"
        "Any other body key, an unknown action, or a `field_path` outside "
        "`mappable_field_paths` is refused with `422` and nothing is written. "
        "That set is a subset of the official schema's paths, so such a refusal "
        "reports what this build can map a note to and never asserts that the "
        "official schema has no such field."
    ),
    response_description=(
        "The note as it now stands, including its full history, and the record's "
        "new `ETag`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_NOTE_NOT_FOUND, **_R_PRECONDITION},
)
def post_note_review(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    note_id: NoteId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"confirmed_by_user\": true, \"action\": \"map|edit|keep|dismiss\", "
            "\"field_path\": \"<required for map>\", \"text\": \"<required for "
            "edit>\", \"reason\": \"<optional for dismiss>\"}`. Any other key is "
            "refused with `422`."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The RECORD's current `ETag`, exactly as a read operation "
            "returned it. Notes have no separate validator of their own."
        ),
    ),
):
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        note = exp.get_note(note_id)
        if note is None:
            return _note_not_found(experiment_id, note_id)
        if not isinstance(body, dict):
            return _note_refusal(
                "invalid_body", "The request body must be a JSON object."
            )
        refused = _unknown_note_keys(body, _NOTE_REVIEW_KEYS)
        if refused is not None:
            return refused
        action = body.get("action")
        if action not in notes.NOTE_ACTIONS - {notes.ACTION_CAPTURE}:
            return _note_refusal(
                "unknown_note_action",
                (
                    "`action` must be one of `map`, `edit`, `keep` or `dismiss`. "
                    "There is no delete: dismissing sets a note aside and leaves it "
                    "readable, and nothing here removes captured content."
                ),
                action=action if isinstance(action, str) else None,
                allowed=[
                    notes.ACTION_MAP,
                    notes.ACTION_EDIT,
                    notes.ACTION_KEEP,
                    notes.ACTION_DISMISS,
                ],
            )
        if body.get("confirmed_by_user") is not True:
            return _confirmation_required("review a note")

        # RESOLVE EVERY INPUT BEFORE ANYTHING IS WRITTEN, so a refused request can
        # never leave a partial act behind.
        if action == notes.ACTION_MAP:
            field_path = body.get("field_path")
            if not isinstance(field_path, str) or field_path not in NOTE_MAPPABLE_FIELD_PATHS:
                return _note_refusal(
                    "unrecognized_field",
                    (
                        "`field_path` must be one of the paths this build can map a "
                        "note to — the list `GET .../notes` reports under "
                        "`mappable_field_paths`. That list is a SUBSET of the "
                        "official schema's field paths, so this refusal says the "
                        "path is not one this application can map a note to; it "
                        "does NOT say the official schema has no such field. An "
                        "invented or misspelt path is refused rather than stored, "
                        "because a note pointing at a target this build cannot "
                        "resolve is a guess with a plausible shape. Nothing was "
                        "written."
                    ),
                    key=field_path if isinstance(field_path, str) else None,
                )
        if action == notes.ACTION_EDIT:
            text_refusal = _note_text_refusal(body.get("text"), what="text")
            if text_refusal is not None:
                return text_refusal
        if action == notes.ACTION_DISMISS and body.get("reason") is not None:
            reason_refusal = _note_text_refusal(body.get("reason"), what="reason")
            if reason_refusal is not None:
                return reason_refusal

        precondition = _check_if_match(if_match, exp)
        if precondition is not None:
            return precondition

        at = _now_iso()
        try:
            if action == notes.ACTION_MAP:
                revised = notes.map_note(note, field_path=body["field_path"], at=at)
            elif action == notes.ACTION_EDIT:
                revised = notes.edit_note(note, text=body["text"], at=at)
            elif action == notes.ACTION_KEEP:
                revised = notes.keep_note(note, at=at)
            else:
                revised = notes.dismiss_note(note, at=at, reason=body.get("reason"))
        except (notes.UnsupportedNote, notes.ImmutableCapture) as refusal:
            # A refusal from the model reaches the client as a typed 422, never as a
            # traceback. `ImmutableCapture` is caught alongside because a review act
            # added later that tried to rewrite the capture must fail loudly at the
            # boundary rather than 500 out of the store.
            return _note_refusal("unsupported_note", str(refusal))

        exp.replace_note(revised)
        _changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another writer won the race; this act was not recorded
        response.headers["ETag"] = exp.etag()
        return {"note": _note_view(revised), "experiment_version": exp.version_token()}


# --- 7e. transcript capture ----------------------------------------------------
#
# THREE OPERATIONS, AND THE SPLIT IS THE DESIGN.
#
# `GET /api/providers/capabilities` is the honest status of the three AI seams,
# read off the resolved implementations rather than off an environment value. It
# existed as a function with no reader; a client that has to decide whether to
# offer a microphone needs the answer from the server, because a string compiled
# into the browser bundle is free to drift from what the deployment actually does.
#
# `POST /api/transcription` is the ONLY consumer of the transcription seam. It
# takes an opaque handle to audio held in the caller's own memory and never audio
# itself: no multipart form is declared anywhere in this application, file upload
# is refused unconditionally, and nothing here opens a socket. In this build the
# seam has no provider, so the operation reports that and transcribes nothing.
#
# `POST /api/experiments/{id}/transcript` is the working path and does not involve
# a provider at all. It reads a transcript a scientist finalized, using this
# repository's own closed table of literal patterns, and it PROPOSES. It writes
# exactly one kind of thing — Unmapped Notes, which are structurally not values and
# not evidence — and it writes them for EVERY segment, so no proposal being
# accepted, and no acceptance succeeding, can lose what was typed.


#: The body keys the transcript operation accepts. Anything else is REFUSED rather
#: than ignored, for the reason the note operations refuse an unknown key: a caller
#: that sends `{"confirmed": true}` alongside its transcript must be told the key
#: means nothing here, not answered 200 while it is dropped.
_TRANSCRIPT_KEYS = frozenset({"text", "finalized", "run_id", "retention"})

#: What produced a note this operation stores. A member of the notes vocabulary,
#: read from it rather than spelled out, so a rename there cannot leave a literal
#: here that the note model would then refuse at capture time.
_TRANSCRIPT_NOTE_SOURCE = "transcript"

#: THE READER MAY NOT PROPOSE A PATH NOBODY CAN ACCEPT, AND THIS IS CHECKED AT
#: IMPORT RATHER THAN BY A REVIEWER NOTICING.
#:
#: The transcript reader holds its own closed table of paths; the run edit holds
#: the set of paths it will write. If the first ever grew a path outside the
#: second, this operation would show a scientist a candidate with an Accept
#: control whose only possible outcome is a refusal — the exact defect the run
#: view's `overridable` flag was added to fix, arriving from the other direction.
#: Failing to construct is louder than any comment.
_UNACCEPTABLE_READER_PATHS = tc.READABLE_FIELD_PATHS - RUN_WRITABLE_FIELD_PATHS
if _UNACCEPTABLE_READER_PATHS:  # pragma: no cover - a construction-time guard
    raise RuntimeError(
        "the transcript reader proposes field paths the run edit will not write: "
        f"{sorted(_UNACCEPTABLE_READER_PATHS)}. A candidate at one of them could "
        "never be accepted."
    )
if _TRANSCRIPT_NOTE_SOURCE not in notes.NOTE_SOURCES:  # pragma: no cover - ditto
    raise RuntimeError(
        f"{_TRANSCRIPT_NOTE_SOURCE!r} is not one of the note sources; a capture "
        "would be refused by the note model at write time."
    )

#: The largest transcript one capture may carry, matching the per-note ceiling
#: because every segment of it becomes a note. Over it is a refusal, never a
#: truncation.
_MAX_TRANSCRIPT_BYTES = _MAX_NOTE_BYTES


def _transcript_refusal(error: str, message: str, **extra) -> JSONResponse:
    """One typed 422. Every refusal on the transcript operation is one of these."""
    return JSONResponse(
        status_code=422, content={"error": error, "message": message, **extra}
    )


def _retention_disclosure(notes_captured: int) -> dict:
    """What this build does with a finalized transcript, and what it will not claim.

    ONE ENFORCED STATE, AND THE ABSENT ONES ARE NAMED. A retention control with
    three options, two of which quietly did nothing, would be worse than no control
    — so the two states this storage cannot enforce are reported as unimplemented
    with the reason, rather than offered and ignored. `deletable` is `false` because
    it is: nothing in this application removes a note, and a deletion guarantee
    that cannot be demonstrated must not be printed next to a scientist's words.
    """
    return {
        "state": tc.RETENTION_ENFORCED_STATE,
        "notes_captured": notes_captured,
        "deletable": False,
        "description": (
            "The finalized transcript is stored with this record as Unmapped "
            "Notes and stays with it. Reviewing a note — including dismissing "
            "one — records a decision and leaves the text readable."
        ),
        "not_implemented": [dict(entry) for entry in tc.RETENTION_STATES_NOT_IMPLEMENTED],
        "raw_audio": {
            "stored": False,
            "reason": (
                "No audio reaches this server. This operation accepts text only, "
                "and the separate transcription operation accepts a handle to "
                "audio the caller holds, never the audio. There is therefore no "
                "raw-audio retention setting, because there is nothing retained "
                "for one to govern."
            ),
        },
    }


def _capabilities_payload() -> dict:
    """The provider report, with the two facts a reader needs beside it."""
    payload = provider_config.capabilities()
    return {
        **payload,
        "note": (
            "`configured` is read off each resolved implementation, not inferred "
            "from an environment value or a class name. Nothing in this build "
            "sets it, so no seam here can report a provider."
        ),
        "manual_transcript_available": True,
    }


@router.get(
    "/providers/capabilities",
    tags=[TAG_META],
    summary="Report Each Model Seam's Status",
    description=(
        "Reports, for each of the three model seams — transcription, capture "
        "extraction, and the assistant — which implementation is resolved, "
        "whether a production provider is configured, and why. Read-only: it "
        "opens no connection, reads no credential, and performs no probe.\n\n"
        "`configured` is read off the resolved implementation itself rather than "
        "inferred from an environment value or a class name, and no "
        "implementation in this build sets it. A client should render this "
        "answer rather than a string compiled into its own bundle, so what a "
        "scientist is told and what the deployment does cannot drift apart.\n\n"
        "`manual_transcript_available` is always `true` and is deliberately "
        "separate from every seam: reading a finalized transcript is this "
        "repository's own deterministic operation and does not depend on any "
        "provider, so it stays available when every seam reports nothing "
        "configured.\n\n"
        "No environment value is echoed back — only which implementation it "
        "resolved to, and the name of the variable that selects it."
    ),
    response_description=(
        "The per-seam status, whether any provider is configured at all, and the "
        "document that records the outstanding decisions."
    ),
    responses={**_R_UNAUTHORIZED},
)
def get_provider_capabilities() -> dict:
    return _capabilities_payload()


@router.post(
    "/transcription",
    tags=[TAG_INGESTION],
    summary="Request a Transcript for Held Audio",
    description=(
        "Asks the transcription seam to turn audio into text. The request "
        "carries an opaque handle naming audio the CALLER holds, and never audio "
        "itself — this application declares no multipart form anywhere, stores no "
        "audio, and this operation opens no outbound connection.\n\n"
        "In this build no transcription provider is configured, so the request is "
        "answered with `501` and a body naming exactly what is missing. That is a "
        "statement about this deployment, not a fault and not a wait: the missing "
        "items are institutional decisions, and the body names the document that "
        "records them.\n\n"
        "Typing or pasting a transcript is the working path and needs none of "
        "this. `POST /api/experiments/{experiment_id}/transcript` reads a "
        "finalized transcript with this repository's own deterministic rules and "
        "is unaffected by any seam's status.\n\n"
        "Supplying neither a handle nor a transcript is `422`: the seam refuses "
        "rather than returning an empty transcript, because an empty transcript "
        "is a legitimate output of a working provider and the two must never "
        "share a shape."
    ),
    response_description=(
        "The transcript, its segmentation by character offset, and whether the "
        "text is exactly what the caller supplied."
    ),
    responses={
        **_R_UNAUTHORIZED,
        501: {
            "description": (
                "No transcription provider is configured for this deployment. The "
                "body names each missing item and the document that records the "
                "decision, and nothing was transcribed, stored, or sent anywhere."
            )
        },
    },
)
def post_transcription(
    body: dict = Body(
        ...,
        description=(
            "`{\"audio_ref\": \"<an opaque handle to audio the caller holds>\", "
            "\"manual_transcript\": \"<text instead of audio>\", \"language\": "
            "\"<optional BCP-47 tag>\"}`. Audio bytes are never accepted."
        ),
    ),
):
    if not isinstance(body, dict):
        return _transcript_refusal(
            "invalid_body", "The request body must be a JSON object."
        )
    audio_ref = body.get("audio_ref")
    manual = body.get("manual_transcript")
    language = body.get("language")
    for name, value in (
        ("audio_ref", audio_ref),
        ("manual_transcript", manual),
        ("language", language),
    ):
        if value is not None and not isinstance(value, str):
            return _transcript_refusal(
                "invalid_field_value",
                f"`{name}` must be a string when it is supplied.",
                key=name,
            )
    provider = provider_config.resolve_transcription_provider()
    outcome = provider.transcribe(
        providers_transcription.TranscriptionRequest(
            audio_ref=audio_ref, manual_transcript=manual, language=language
        )
    )
    if outcome.refused:
        # TWO REFUSAL REASONS, TWO STATUS CODES, and collapsing them would be the
        # error. "This build does not do that" is a fact about the deployment and
        # is `501`; "you sent nothing to work on" is a fact about the request and
        # is `422`. A client that retried the first would be waiting for something
        # nobody has decided to build.
        unconfigured = outcome.reason == providers_refusal.REASON_NO_PROVIDER_CONFIGURED
        return JSONResponse(
            status_code=501 if unconfigured else 422, content=outcome.to_dict()
        )
    return outcome.to_dict()


#: The body keys the assistant seam accepts. A closed set for the same reason the
#: transcript operation's is closed: a caller that sends `{"record_id": "..."}`
#: expecting the server to fetch context must be told the key means nothing here,
#: not answered with an answer built from context it did not send.
_ASSISTANT_KEYS = frozenset({"question", "context"})

#: The keys ONE context item may carry. `providers/assistant.ContextItem` requires
#: all three and refuses a partial one at construction, which is where the rule
#: lives; this set is what makes an UNKNOWN key a refusal rather than a silent drop.
_ASSISTANT_CONTEXT_KEYS = frozenset({"key", "text", "origin"})


@router.post(
    "/assistant/ask",
    tags=[TAG_ASSISTANT],
    summary="Ask the Assistant Seam a Grounded Question",
    description=(
        "Asks the assistant seam a question, answerable ONLY from context the "
        "request itself supplies. This operation fetches nothing: it cannot read a "
        "record, a workspace, or a database, so \"what was sent to the provider\" "
        "is exactly the `context` array in the request body and is visible to the "
        "caller who wrote it.\n\n"
        "AN ANSWER CITES ITS CONTEXT OR THERE IS NO ANSWER. Every answer carries "
        "`grounded_in`, the context keys it used, and an uncited answer cannot be "
        "constructed — `AssistantAnswer` raises. A question the supplied context "
        "does not cover is REFUSED rather than answered from general knowledge, "
        "which is the no-guessing rule applied to the assistant's own prose and not "
        "only to the fields it might propose.\n\n"
        "NOTHING HERE IS A VERDICT. `authoritative` is a constant `false`. This "
        "operation decides nothing about validity, exportability or scientific "
        "correctness, writes no field, advances no revision, and is absent from the "
        "validation stack entirely — draft validation, official schema validation, "
        "the portal warning tier, advisory review and a human are unchanged.\n\n"
        "IN THIS BUILD NO ASSISTANT PROVIDER IS CONFIGURED, so every request that "
        "REACHES the seam is answered `501` with a body naming exactly what is "
        "missing and the document that records the decision. A malformed request "
        "never reaches it and is `422`, as below. That is a statement about this deployment rather "
        "than a fault or a wait: the missing items are institutional decisions. The "
        "deterministic fake is deliberately unreachable through a booted "
        "application, so no deployment can answer from it and no screen may show a "
        "connected state.\n\n"
        "A `422` here means the request is not askable — no question, a context item "
        "missing its `key`, `text` or `origin`, or an unrecognised key — or that the "
        "context supplied does not cover the question. Nothing is sent anywhere in "
        "either case, and the two are distinguished by the `error` in the body.\n\n"
        "The working, shipped way to ask this application a question is "
        "`POST /api/assistant/memory/query`, which routes a bounded catalogue of "
        "intents over committed deterministic sources and involves no provider at "
        "all. It is unaffected by this seam's status."
    ),
    response_description=(
        "The answer, the context keys it cites, and what produced it — with "
        "`authoritative: false`."
    ),
    responses={
        # NO EXPLICIT `422` ENTRY, and that is not an omission. Declaring one makes
        # FastAPI skip generating its own, which silently strips the
        # `HTTPValidationError` content ref every operation with a request body is
        # required to carry — `test_operations_with_parameters_keep_the_validation_error_schema`
        # caught exactly that here. The transcription seam has the same shape for the
        # same reason. What a 422 MEANS on this operation is stated in the description
        # instead, where a reader will actually see it.
        **_R_UNAUTHORIZED,
        501: {
            "description": (
                "No assistant provider is configured for this deployment. The body "
                "names each missing item and the document that records the "
                "decision, and nothing was answered or sent anywhere."
            )
        },
    },
)
def post_assistant_ask(
    body: dict = Body(
        ...,
        description=(
            "`{\"question\": \"...\", \"context\": [{\"key\": \"...\", "
            "\"text\": \"...\", \"origin\": \"...\"}]}`. `context` is the "
            "ONLY material an answer may be built from, and `origin` is the "
            "caller's own statement of where each item came from."
        ),
    ),
):
    if not isinstance(body, dict):
        return _transcript_refusal(
            "invalid_body", "The request body must be a JSON object."
        )
    unknown = sorted(set(body) - _ASSISTANT_KEYS)
    if unknown:
        # REFUSED, NOT IGNORED. A caller sending `record_id` is asking this
        # operation to fetch something, and answering 200 while dropping the key
        # would leave them believing the answer was grounded in a record nobody
        # read.
        return _transcript_refusal(
            "unrecognized_field",
            "This operation supplies no context of its own, so it accepts only "
            "`question` and `context`. Nothing was sent anywhere.",
            keys=unknown,
        )
    question = body.get("question")
    if not isinstance(question, str) or not question.strip():
        return _transcript_refusal(
            "invalid_field_value",
            "`question` must be a non-empty string.",
            key="question",
        )
    raw_context = body.get("context")
    if raw_context is None:
        raw_context = []
    if not isinstance(raw_context, list):
        return _transcript_refusal(
            "invalid_field_value",
            "`context` must be a list of items, each with `key`, `text` and "
            "`origin`.",
            key="context",
        )
    items: list[providers_assistant.ContextItem] = []
    for index, entry in enumerate(raw_context):
        if not isinstance(entry, dict):
            return _transcript_refusal(
                "invalid_field_value",
                "Each context item must be an object.",
                key=f"context[{index}]",
            )
        extra = sorted(set(entry) - _ASSISTANT_CONTEXT_KEYS)
        if extra:
            return _transcript_refusal(
                "unrecognized_field",
                "A context item carries exactly `key`, `text` and `origin`.",
                key=f"context[{index}]",
                keys=extra,
            )
        try:
            items.append(
                providers_assistant.ContextItem(
                    key=entry.get("key"),  # type: ignore[arg-type]
                    text=entry.get("text"),  # type: ignore[arg-type]
                    origin=entry.get("origin"),  # type: ignore[arg-type]
                )
            )
        except (ValueError, TypeError):
            # `ContextItem.__post_init__` is where the rule lives — "unattributed
            # context is how an answer loses its grounding" — so this branch
            # RELAYS its refusal rather than re-implementing the check. A second
            # copy of the rule here is a second thing to keep in step.
            return _transcript_refusal(
                "invalid_field_value",
                "A context item must have a non-empty `key`, `text` and `origin`. "
                "Unattributed context is refused rather than sent.",
                key=f"context[{index}]",
            )

    provider = provider_config.resolve_assistant_provider()
    outcome = provider.answer(
        providers_assistant.AssistantRequest(
            question=question, grounded_context=tuple(items)
        )
    )
    if outcome.refused:
        # THE SAME TWO-CODE SPLIT THE TRANSCRIPTION SEAM MAKES, and for the same
        # reason: "this build does not do that" is a fact about the deployment and
        # is `501`, while "the context you sent does not cover this" is a fact
        # about the request and is `422`. A client that retried the first would be
        # waiting for an institutional decision nobody has taken.
        unconfigured = outcome.reason == providers_refusal.REASON_NO_PROVIDER_CONFIGURED
        return JSONResponse(
            status_code=501 if unconfigured else 422, content=outcome.to_dict()
        )
    return outcome.to_dict()


@router.post(
    "/experiments/{experiment_id}/transcript",
    tags=[TAG_EXPERIMENTS],
    summary="Read a Finalized Transcript into Candidates and Notes",
    description=(
        "Reads one transcript a scientist has explicitly finalized, stores it "
        "verbatim with the record, and returns the field values it PROPOSES — "
        "plus every ambiguity it refused to resolve.\n\n"
        "`finalized` must be `true`. There is no partial pass and no reading "
        "while text is still being typed: a request without it is `422` and "
        "nothing is stored, so text that is still being written can never move a "
        "value.\n\n"
        "NOTHING HERE IS A VALUE. Every proposal is a candidate carrying the "
        "words it came from, the rule that read them, `verified: false`, "
        "`is_evidence: false` and a `status` of `needs_confirmation`, which are "
        "constants of the shape rather than fields a request can set. A candidate "
        "becomes a value only when a person accepts it through "
        "`PATCH /api/experiments/{experiment_id}/runs/{run_id}` with "
        "`confirmed_by_user: true` and that run's own `ETag` — this operation "
        "writes no field, and `accept_contract` in the response says where the "
        "write happens.\n\n"
        "EVERY SEGMENT OF THE TRANSCRIPT BECOMES AN UNMAPPED NOTE, including the "
        "segments that produced a candidate. That redundancy is deliberate: a "
        "candidate is not stored anywhere, so rejecting one — or failing to "
        "accept it — would otherwise destroy the words behind it. `retention` "
        "reports the one storage state this build enforces and names the states "
        "it does not offer, rather than presenting a control that would do "
        "nothing.\n\n"
        "AMBIGUITY IS NEVER RESOLVED BY PREFERENCE. A run named by position, a "
        "run this record does not have, a run matching more than one, and a run "
        "other than the one this capture is addressed to each produce a "
        "clarification listing the alternatives. Two statements giving different "
        "values for one field produce both candidates grouped for review, with "
        "neither dropped. A temperature in another unit, and the absorbing "
        "element or absorption edge, each produce an abstention with the reason. "
        "Everything else is stored as a note. `ambiguity_policy` in the response "
        "states each rule.\n\n"
        "CANDIDATES ARE WITHHELD WHENEVER THE RUN IS UNSETTLED — when no run was "
        "selected, and whenever any run clarification was raised. A proposal a "
        "scientist could accept against the wrong run is worse than no proposal, "
        "and the transcript is stored either way.\n\n"
        "Storing the transcript rewrites the record, so this requires the "
        "RECORD's current `ETag` in `If-Match` — omitted is `428`, malformed is "
        "`400`, and stale is `412` with nothing written. Text too large, or a "
        "transcript that would exceed the segment ceiling, is REFUSED rather than "
        "shortened. `retention` accepts only the state this build enforces; any "
        "other value is `422` naming what is enforced."
    ),
    response_description=(
        "The proposed candidates, the clarifications, abstentions and conflicts "
        "the reader refused to resolve, the notes it stored, the retention state, "
        "and the record's new `ETag`."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_TUTORIAL_SCOPE,
        **_R_PRECONDITION,
    },
)
def post_transcript(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"text\": \"<the finalized transcript>\", \"finalized\": true, "
            "\"run_id\": \"<the run these notes describe>\", \"retention\": "
            "\"<the enforced retention state>\"}`. Any other key is refused with "
            "`422`."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The RECORD's current `ETag`, exactly as a read operation "
            "returned it. The transcript is stored inside the record's own "
            "document, so there is no separate validator for it."
        ),
    ),
):
    # Existence pre-check OUTSIDE the lock, as every other mutation does it, so a
    # bogus id never pins a permanent entry in the never-evicting lock map.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        if not isinstance(body, dict):
            return _transcript_refusal(
                "invalid_body", "The request body must be a JSON object."
            )
        refused = _unknown_note_keys(body, _TRANSCRIPT_KEYS)
        if refused is not None:
            return refused
        # THE FINALIZE GATE IS THE FIRST CHECK AND IS UNCONDITIONAL. It is checked
        # before the precondition, before the text, and before anything is read, so
        # there is no ordering in which unfinished text reaches the reader.
        if body.get("finalized") is not True:
            return _transcript_refusal(
                "finalize_required",
                (
                    "`finalized` must be true. A transcript is read only when a "
                    "person says it is finished — there is no reading of text that "
                    "is still being written, and nothing was stored."
                ),
            )
        raw_text = body.get("text")
        text_refusal = _note_text_refusal(raw_text, what="text")
        if text_refusal is not None:
            return text_refusal
        if not _is_storable_value(raw_text, max_bytes=_MAX_TRANSCRIPT_BYTES):
            return _transcript_refusal(
                "unrepresentable_value",
                (
                    "This transcript could not be stored intact. It is REFUSED "
                    "rather than shortened, because a shortened transcript "
                    "misrepresents what was said. Nothing was stored."
                ),
            )
        retention = body.get("retention", tc.RETENTION_ENFORCED_STATE)
        if retention != tc.RETENTION_ENFORCED_STATE:
            return _transcript_refusal(
                "unsupported_retention",
                (
                    "This build enforces one retention state and will not accept "
                    "another. The states it does not offer are reported with the "
                    "reason, and nothing was stored."
                ),
                retention=retention if isinstance(retention, str) else None,
                enforced=tc.RETENTION_ENFORCED_STATE,
                not_implemented=[
                    dict(entry) for entry in tc.RETENTION_STATES_NOT_IMPLEMENTED
                ],
            )
        run_id = body.get("run_id")
        if run_id is not None and (
            not isinstance(run_id, str) or exp.get_run(run_id) is None
        ):
            return _transcript_refusal(
                "unknown_run",
                (
                    "This record has no run with that id, so a transcript cannot "
                    "be addressed to it. Omit `run_id` to store the transcript "
                    "against the record and be asked which run it describes — it "
                    "is never inferred."
                ),
                run_id=run_id if isinstance(run_id, str) else None,
            )

        known_runs = tuple(
            tc.RunRef(
                id=run.id,
                label=run.label,
                ordinal=run.ordinal,
                record_id=run.record_id,
            )
            for run in exp.sorted_runs()
        )
        reading = tc.read_transcript(
            raw_text, selected_run=run_id, known_runs=known_runs
        )
        if len(reading.segments) > tc.MAX_SEGMENTS:
            return _transcript_refusal(
                "transcript_too_long",
                (
                    "This transcript is longer than one capture may store. It is "
                    "REFUSED whole rather than partly stored, because a partly "
                    "stored transcript loses words without saying which. Nothing "
                    "was stored; finalize it in smaller pieces."
                ),
                segments=len(reading.segments),
                maximum=tc.MAX_SEGMENTS,
            )

        precondition = _check_if_match(if_match, exp)
        if precondition is not None:
            return precondition

        # EVERY SEGMENT IS STORED, and the candidate a segment produced is recorded
        # on its note ONLY when the segment produced exactly one — a note carries
        # one candidate path, and writing one of two there would state a preference
        # this reader does not hold.
        captured: list["notes.Note"] = []
        try:
            for segment in reading.segments:
                candidate = reading.candidate_for_segment(segment.index)
                captured.append(
                    exp.capture_note(
                        text=segment.text,
                        source=_TRANSCRIPT_NOTE_SOURCE,
                        run_id=run_id,
                        candidate_field_path=(
                            candidate.field_path if candidate is not None else None
                        ),
                        candidate_rule=candidate.rule if candidate is not None else None,
                    )
                )
        except notes.UnsupportedNote as refusal:
            # The model's own refusals reach the client as a typed 422, never a 500.
            # Nothing was saved: `capture_note` mutates the in-memory record only,
            # and the save below has not run.
            return _transcript_refusal("unsupported_note", str(refusal))

        _changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another writer won the race; nothing was stored

        response.headers["ETag"] = exp.etag()
        return {
            "capture": {
                "finalized": True,
                "run_id": run_id,
                "segments": len(reading.segments),
                "retention": _retention_disclosure(len(captured)),
            },
            # `applied` is a constant on the reading and is serialised so a client
            # reading JSON sees the guarantee rather than having to know it.
            "applied": reading.applied,
            "candidates": [candidate.to_dict() for candidate in reading.candidates],
            "clarifications": [entry.to_dict() for entry in reading.clarifications],
            "abstentions": [entry.to_dict() for entry in reading.abstentions],
            "review_required": [entry.to_dict() for entry in reading.review_required],
            "notes": [_note_view(note) for note in captured],
            "ambiguity_policy": [dict(entry) for entry in tc.AMBIGUITY_POLICY],
            # THE SERVER'S OWN ANSWER TO "WHERE DOES ACCEPTING WRITE?", for the
            # reason the notes list reports its mappable paths: the alternative is
            # a second copy of the write contract in the browser bundle, free to
            # drift from the operation that enforces it.
            "accept_contract": {
                "method": "PATCH",
                "path": "/api/experiments/{experiment_id}/runs/{run_id}",
                "requires": [
                    "confirmed_by_user: true",
                    "If-Match set to that run's own current ETag",
                ],
                "message": (
                    "This operation writes no field. A candidate becomes a value "
                    "only through that request, made by a person who accepted it."
                ),
            },
            "experiment_version": exp.version_token(),
        }


# --- 7b. asset references ------------------------------------------------------
#
# FOUR OPERATIONS OVER METADATA ABOUT FILES. NO BYTES, EVER.
#
# An asset reference records where a file is (`uri`), what role it plays
# (`content_role`), and the digest the scientist says identifies it (`sha256`).
# Nothing in this section opens a file, fetches a URI, accepts an upload or
# computes a hash. `POST /api/uploads` is still an unconditional 403 and this
# feature neither changes nor depends on it; no multipart parser is reachable from
# here.
#
# WHY THESE ROUTES EXIST AT ALL. Before them, the only way a human could touch an
# asset was to paste a digest into `GuidedPrompt` for an asset the extractor had
# already detected — `apply_answers` is what CREATES the entry, from a blocker, so
# a person could not originate one. That path is untouched and still works
# (`_answers_to_apply_shape`); these routes are the missing "author one yourself".
#
# ONE VALIDATOR, THE RECORD'S. Every write here rewrites the experiment document —
# the library lives in `experiment.draft["assets"]` and the associations live in
# each run's `draft["assets"]`, and both are inside that one document. So all three
# writes take the RECORD's `If-Match`, never a run's, exactly as `POST .../runs`
# does for the same reason. The two stores are rewritten together inside one
# `record_lock` and one save, which is what stops them drifting.

#: The path parameter naming an asset reference. One description, so the wording
#: cannot drift between the two operations that take it.
AssetId = Annotated[
    str,
    Path(
        description=(
            "The `asset_id` of an asset reference on this record, as returned by "
            "`GET /api/experiments/{experiment_id}/assets`."
        )
    ),
]

#: The question a CREATE records itself as answering, in the evidence entry.
#:
#: It says "recorded", never "verified", and it does not mention the file — because
#: what the person confirmed is that these are the values they mean to store, and
#: this application has not opened anything at the URI to confirm anything else. An
#: evidence entry is read later by someone deciding whether to trust a record; a
#: question that overstated what was checked would mislead exactly there.
_ASSET_CREATE_QUESTION = (
    "Record these asset reference details, as entered? (No file was read, fetched "
    "or hashed by this application.)"
)


def _asset_edit_question(asset_id: str) -> str:
    """The question an EDIT records itself as answering. Same care as the create one."""
    return (
        f"Change these details of asset reference {asset_id}, as entered? (No file "
        "was read, fetched or hashed by this application.)"
    )


_R_ASSET_NOT_FOUND: dict = {
    404: {
        "description": (
            "No experiment in the selected workspace has that id, that record holds "
            "no asset reference under that `asset_id`, or the "
            "`X-Isaac-Tutorial-Session` header named a worked-example session that "
            "does not exist. The request is never silently answered from the "
            "ordinary workspace instead."
        )
    },
}


def _asset_not_found(experiment_id: str, asset_id: str) -> JSONResponse:
    """An asset this record does not hold. Distinct from `_not_found`.

    Same reasoning as :func:`_run_not_found` and :func:`_note_not_found`: the two
    404s mean different things — one says the workspace has no such record, this one
    says the record was read successfully and holds no asset under that id — and
    collapsing them sends a client looking in the wrong place.
    """
    return JSONResponse(
        status_code=404,
        content={
            "error": "asset_not_found",
            "experiment_id": experiment_id,
            "id": asset_id,
        },
    )


def _asset_refusal(exc: "assets.UnsupportedAsset") -> JSONResponse:
    """The domain model's own refusal, rendered as a typed 422 — never a 500.

    `complete.py` type-guards `series` and `descriptor` because a wrong-typed
    structured answer used to escape the truth core as an HTTP 500; a new write
    surface must not reopen that. Every shape `isaac_api.assets` refuses arrives
    here carrying its own error code and its own extra body keys, so a malformed
    payload can never surface as a traceback.
    """
    return JSONResponse(
        status_code=422,
        content={"error": exc.error, "message": exc.message, **exc.extra},
    )


def _asset_view(exp: Experiment, entry: dict) -> dict:
    """One asset reference, as this API presents it.

    THREE DERIVED FACTS ARE ADDED, and each exists because a client would otherwise
    have to compute it — which would put a second, drifting opinion in the browser:

    * ``used_by_runs`` — every run whose own draft carries this asset, with its
      label and ordinal, so "where is this used?" is answerable without N reads.
    * ``export_reach`` — where this asset actually reaches an exported record. See
      :func:`assets.export_reach`; ``none`` is the answer that has to exist, because
      a library entry on a record that HAS runs and is associated with none of them
      is invisible to export, and a scientist who is not told that will never find
      out.
    * ``sha256_wellformed`` — whether the stored digest is 64 lowercase hex
      characters. **It is a statement about the STRING, not about the file.** This
      application never reads the file at the URI, so it cannot and does not report
      that a digest matches anything. The key is named for what it measures.

    ``evidence`` is deep-copied on the way out for the reason
    ``resolve_inherited`` copies its payloads: handing back a live reference into the
    stored document lets a caller write through a read.
    """
    asset_id = entry.get("asset_id")
    associated = set(assets.associated_run_ids(exp, asset_id))
    stored_evidence = entry.get(assets.EVIDENCE_KEY)
    evidence = list(stored_evidence) if isinstance(stored_evidence, list) else []
    return {
        **{k: v for k, v in entry.items() if k != assets.EVIDENCE_KEY},
        "evidence": copy.deepcopy(evidence),
        "evidence_count": len(evidence),
        "sha256_wellformed": is_sha256_shaped(entry.get("sha256")),
        "used_by_runs": [
            {"run_id": run.id, "label": run.label, "ordinal": run.ordinal}
            for run in exp.sorted_runs()
            if run.id in associated
        ],
        "export_reach": assets.export_reach(exp, asset_id),
    }


def _assets_payload(exp: Experiment) -> dict:
    """The listing body.

    ``content_roles`` is served from the vendored official schema rather than from a
    list written here, so the twelve values a client renders in a control are the
    twelve the exported record is validated against. ``runs`` is included because
    associating an asset needs the record's runs and a client should not have to
    make a second read to draw the control.
    """
    entries = assets.library(exp.draft)
    return {
        "assets": [_asset_view(exp, entry) for entry in entries],
        "total": len(entries),
        # A DISCLOSURE OF WHAT THIS BUILD CANNOT PRESENT, counted rather than
        # rendered and never removed from the document. Two kinds, deliberately not
        # separated: an entry that is not an object, and one carrying no `asset_id`
        # (which no route could address). Both stay in the record untouched.
        #
        # `_everywhere`, not `unreadable_count(exp.draft)`. The disclosure must
        # cover the same ground the REFUSAL does: `refuse_unreadable_containers`
        # checks the experiment AND every run, so a run-held unreadable container
        # used to read as a clean `0` here and then 422 on the very next write,
        # naming a run the reader had been told nothing about.
        "unreadable_entries": assets.unreadable_count_everywhere(exp),
        "content_roles": list(assets.content_roles()),
        "runs": [
            {"id": run.id, "label": run.label, "ordinal": run.ordinal}
            for run in exp.sorted_runs()
        ],
        "experiment_version": exp.version_token(),
    }


def _resolve_run_ids(exp: Experiment, raw: object) -> tuple[set[str] | None, JSONResponse | None]:
    """``run_ids`` as a set, or a typed 422. Absent means "leave associations alone".

    WHOLE-SET SEMANTICS, not add/remove. A scientist is stating which runs use this
    file; an add-only API would make "none of them" unreachable, and a diff-based one
    would need the client to know the current set to express the new one.

    A run id this record does not have is a `422`, not a `404`: the record exists,
    the request is about an asset, and what is wrong is one entry of one body field.
    Nothing is inferred — naming no runs on a record with exactly one run does NOT
    associate it with that one.
    """
    if raw is None:
        return None, None
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        return None, JSONResponse(
            status_code=422,
            content={
                "error": "invalid_run_ids",
                "message": (
                    "`run_ids` must be a list of run ids. Send `[]` to associate this "
                    "asset with no run, or omit the key to leave its associations "
                    "unchanged. Nothing was written."
                ),
            },
        )
    known = {run.id for run in exp.sorted_runs()}
    unknown = sorted(set(raw) - known)
    if unknown:
        return None, JSONResponse(
            status_code=422,
            content={
                "error": "unknown_run",
                "message": (
                    "This record has no run with that id, so an asset cannot be "
                    "associated with it. Run ids come from "
                    "`GET /api/experiments/{experiment_id}/runs`; none is inferred. "
                    "Nothing was written."
                ),
                "run_id": unknown[0],
                "run_ids": unknown,
            },
        )
    return set(raw), None


def _asset_storable(entry: dict) -> JSONResponse | None:
    """Bound what one asset entry may cost, with the guard every write path uses.

    `_is_storable_value` is bounded size, bounded depth and real renderability —
    the three conditions its own docstring records were each added after a measured
    wedged-record defect. An asset is caller-shaped free text (`notes`,
    `caption_verbatim`) plus two open objects (`citation`, `caption_highlights`),
    so it is exactly the payload that guard exists for.
    """
    if _is_storable_value(entry):
        return None
    return JSONResponse(
        status_code=422,
        content={
            "error": "unrepresentable_value",
            "message": (
                "This asset reference could not be stored intact — it is larger or "
                "more deeply nested than one entry may be, or it contains characters "
                "JSON cannot represent (a lone surrogate), so a record containing it "
                "could not be read back. It is REFUSED rather than shortened. Nothing "
                "was written."
            ),
        },
    )


_ASSETS_LIST_DESCRIPTION = (
    "Lists the asset references on this record — metadata about files, never the "
    "files themselves. Each entry carries the official ISAAC asset fields, the "
    "evidence recorded for it, the runs it is associated with, and where it "
    "actually reaches an exported record. Read-only.\n\n"
    "NO FILE IS READ, FETCHED OR HASHED BY THIS APPLICATION. `sha256_wellformed` "
    "says whether the stored digest is 64 lowercase hexadecimal characters — a "
    "statement about the string, not about the file at the `uri`, which this server "
    "has never opened. Nothing here should be presented as a verified or checked "
    "hash.\n\n"
    "`export_reach` is `record` when this experiment has no runs (it exports one "
    "record from its own draft, carrying this asset), `runs` when the asset is "
    "associated with at least one run, and `none` when the experiment HAS runs and "
    "this asset is associated with none of them — in which case no exported record "
    "will carry it, because assets are run-level content.\n\n"
    "`content_roles` is the official schema's own enumeration, read from the "
    "vendored schema rather than restated, so a client renders exactly the values "
    "the exported record is validated against. `unreadable_entries` counts stored "
    "entries this build cannot present — one that is not an object, or one carrying "
    "no `asset_id` — which are left in the record untouched rather than dropped."
)

_ASSETS_CREATE_DESCRIPTION = (
    "Records one asset reference on this record and returns it. Metadata only: no "
    "file is uploaded, opened, fetched or hashed, and this operation accepts no "
    "file content of any kind.\n\n"
    "THE DIGEST IS YOURS, NOT THIS SERVER'S. `sha256` must be exactly 64 lowercase "
    "hexadecimal characters, with nothing before or after it — not even a trailing "
    "newline. It is never computed, completed, trimmed or corrected: this "
    "application does not read the file at the `uri`, so the only digest it can hold "
    "is the one you supply, and a malformed one is refused with `422` rather than "
    "repaired.\n\n"
    "`asset_id`, `content_role`, `uri` and `sha256` are required — the official ISAAC "
    "schema requires them and none is invented here. `asset_id` must be unique on "
    "this record, because the evidence sidecar is keyed by it. `content_role` must be "
    "one of the twelve values the official schema enumerates; it is not inferred from "
    "the URI, the file extension or the media type. Any key the official schema does "
    "not declare on an asset is refused with `422` naming it, because that object is "
    "closed and storing one would make the record unexportable.\n\n"
    "`run_ids` associates this asset with those runs, and `[]` or an omitted key "
    "associates it with none — nothing is chosen on your behalf, including on a "
    "record that has exactly one run. Recording an asset rewrites the record, so "
    "this requires `confirmed_by_user: true` and the RECORD's current `ETag` in "
    "`If-Match` — omitted is `428`, malformed is `400`, and stale is `412` with "
    "nothing written."
)

_ASSETS_UPDATE_DESCRIPTION = (
    "Edits the draft metadata of one asset reference, its run associations, or "
    "both, and returns the refreshed entry. Metadata only: no file is uploaded, "
    "opened, fetched or hashed.\n\n"
    "Only the keys you send are changed; a key you omit keeps its current value. "
    "Sending `null` clears an optional key by removing it — a stored `null` would "
    "fail official validation. The four required keys cannot be cleared; remove the "
    "whole reference instead. `asset_id` cannot be changed: it is the address of "
    "this entry, the key of every run's copy of it and the key of its evidence "
    "sidecar entry, so sending a different one is refused with `422`.\n\n"
    "A new `sha256` is subject to the same rule as on creation — exactly 64 "
    "lowercase hexadecimal characters, never computed or repaired here. `run_ids` "
    "SETS the associations exactly: `[]` associates the asset with no run, and "
    "omitting the key leaves them unchanged.\n\n"
    "Every change appends a user confirmation to this asset's evidence; nothing "
    "already recorded is replaced or removed. A request that changes nothing is a "
    "no-op that does not advance the record's revision. A request that names no "
    "asset field and no `run_ids` is refused with `422` rather than silently doing "
    "nothing. Requires `confirmed_by_user: true` and the RECORD's current `ETag` in "
    "`If-Match`."
)

_ASSETS_REMOVE_DESCRIPTION = (
    "Removes one asset reference from this record's draft and from every run that "
    "was associated with it, and reports what was removed.\n\n"
    "This deletes a DRAFT reference — the metadata entry this application holds. It "
    "does not touch the file at the `uri`, which this application has never read, "
    "and it does not alter any record already exported: an exported record and its "
    "evidence sidecar are written artifacts and are not rewritten by this "
    "operation.\n\n"
    "The evidence recorded on the reference is removed with it, because it is part "
    "of the entry. Requires `confirmed_by_user: true` and the RECORD's current "
    "`ETag` in `If-Match` — omitted is `428`, malformed is `400`, and stale is `412` "
    "with nothing removed."
)


@router.get(
    "/experiments/{experiment_id}/assets",
    tags=[TAG_EXPERIMENTS],
    summary="List a Record's Asset References",
    description=_ASSETS_LIST_DESCRIPTION,
    response_description=(
        "The record's asset references, the official `content_role` vocabulary, the "
        "record's runs, and the record's current `ETag`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_TUTORIAL_SCOPE},
)
def list_assets(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    response.headers["ETag"] = exp.etag()
    return _assets_payload(exp)


@router.post(
    "/experiments/{experiment_id}/assets",
    tags=[TAG_EXPERIMENTS],
    status_code=201,
    summary="Record an Asset Reference",
    description=_ASSETS_CREATE_DESCRIPTION,
    response_description=(
        "The stored asset reference and the record's new revision, with the record's "
        "new `ETag`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_TUTORIAL_SCOPE, **_R_PRECONDITION},
)
def post_asset(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"confirmed_by_user\": true, \"asset_id\": \"<unique on this "
            "record>\", \"content_role\": \"<one of the twelve schema values>\", "
            "\"uri\": \"<where the file is>\", \"sha256\": \"<64 lowercase hex "
            "characters>\", \"run_ids\": [\"<optional>\"]}`, plus any optional "
            "official asset field. Any other key is refused with `422`."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The RECORD's current `ETag`, exactly as a read operation "
            "returned it. Asset references have no validator of their own."
        ),
    ),
):
    # Existence pre-check OUTSIDE the lock, exactly as every other mutation does it,
    # so a bogus id never pins a permanent entry in the never-evicting lock map.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=422,
                content={
                    "error": "invalid_body",
                    "message": "The request body must be a JSON object.",
                },
            )
        if body.get("confirmed_by_user") is not True:
            return _confirmation_required("record an asset reference")
        # REFUSE BEFORE WRITING IF A STORED CONTAINER IS UNREADABLE. See
        # `assets.refuse_unreadable_containers`: every read surface promises that what
        # this build cannot present is kept unchanged, and rewriting a non-list
        # `assets` would break that promise silently.
        try:
            assets.refuse_unreadable_containers(exp)
        except assets.UnsupportedAsset as refusal:
            return _asset_refusal(refusal)
        # EVERY INPUT IS RESOLVED BEFORE THE PRECONDITION IS CHECKED, so a malformed
        # request is a 422 whether or not the caller's `If-Match` happens to be
        # current — the ordering `post_note` and `post_run` both use.
        try:
            entry = assets.build_asset(
                body,
                timestamp=_now_iso(),
                question=_ASSET_CREATE_QUESTION,
            )
        except assets.UnsupportedAsset as refusal:
            return _asset_refusal(refusal)
        unstorable = _asset_storable(entry)
        if unstorable is not None:
            return unstorable
        if assets.find(exp.draft, entry["asset_id"]) is not None:
            return _asset_refusal(
                assets.UnsupportedAsset(
                    "duplicate_asset_id",
                    (
                        f"This record already has an asset reference called "
                        f"{entry['asset_id']!r}. Ids must be unique: the evidence "
                        "sidecar is keyed by them, so two entries sharing one id "
                        "would publish a single evidence list and lose the other. "
                        "Nothing was written."
                    ),
                    key="asset_id",
                )
            )
        run_ids, run_refusal = _resolve_run_ids(exp, body.get("run_ids"))
        if run_refusal is not None:
            return run_refusal
        precondition = _check_if_match(if_match, exp)
        if precondition is not None:
            return precondition
        try:
            assets.upsert(exp, entry, creating=True)
        except assets.UnsupportedAsset as refusal:  # pragma: no cover - guarded above
            return _asset_refusal(refusal)
        # `set_associations` with an explicit set writes the asset onto exactly those
        # runs; `None` (the key omitted) leaves every run without it, because a
        # brand-new asset is associated with nothing until someone says otherwise.
        assets.set_associations(exp, entry, run_ids or set())
        _changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another writer won the race; this asset was not recorded
        response.headers["ETag"] = exp.etag()
        return {
            "asset": _asset_view(exp, entry),
            "experiment_version": exp.version_token(),
        }


@router.patch(
    "/experiments/{experiment_id}/assets/{asset_id}",
    tags=[TAG_EXPERIMENTS],
    summary="Edit One Asset Reference",
    description=_ASSETS_UPDATE_DESCRIPTION,
    response_description="The refreshed asset reference, with the record's new `ETag`.",
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_ASSET_NOT_FOUND, **_R_PRECONDITION},
)
def patch_asset(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    asset_id: AssetId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"confirmed_by_user\": true, <any official asset field to change>, "
            "\"run_ids\": [\"<optional, sets the associations exactly>\"]}`. A "
            "`null` clears an optional field. `asset_id` may only repeat the one in "
            "the path. Any other key is refused with `422`."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The RECORD's current `ETag`, exactly as a read operation "
            "returned it."
        ),
    ),
):
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        existing = assets.find(exp.draft, asset_id)
        if existing is None:
            return _asset_not_found(experiment_id, asset_id)
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=422,
                content={
                    "error": "invalid_body",
                    "message": "The request body must be a JSON object.",
                },
            )
        if body.get("confirmed_by_user") is not True:
            return _confirmation_required("edit an asset reference")
        try:
            assets.refuse_unreadable_containers(exp)
        except assets.UnsupportedAsset as refusal:
            return _asset_refusal(refusal)
        if "asset_id" in body and body["asset_id"] != asset_id:
            return _asset_refusal(
                assets.UnsupportedAsset(
                    "immutable_asset_id",
                    (
                        "`asset_id` cannot be changed. It is the address of this "
                        "entry, the key of every run's copy of it and the key of its "
                        "evidence sidecar entry, so a rename would have to move all "
                        "three at once. Record a new reference and remove this one "
                        "instead. Nothing was written."
                    ),
                    key="asset_id",
                )
            )
        # A BODY THAT NAMES NOTHING IS REFUSED, NOT SILENTLY HONOURED. `patch_run`
        # takes the same position for the same reason: answering 200 to a request
        # that could not have changed anything reports a write that did not happen.
        touched = [key for key in body if key not in ("confirmed_by_user", "asset_id")]
        if not touched:
            return _asset_refusal(
                assets.UnsupportedAsset(
                    "empty_update",
                    (
                        "This request names no asset field to change and no "
                        "`run_ids`, so there is nothing to apply. It is refused "
                        "rather than answered as though something had been written."
                    ),
                )
            )
        try:
            entry = assets.build_asset(
                body,
                existing=existing,
                timestamp=_now_iso(),
                question=_asset_edit_question(asset_id),
            )
        except assets.UnsupportedAsset as refusal:
            return _asset_refusal(refusal)
        unstorable = _asset_storable(entry)
        if unstorable is not None:
            return unstorable
        run_ids, run_refusal = _resolve_run_ids(exp, body.get("run_ids"))
        if run_refusal is not None:
            return run_refusal
        precondition = _check_if_match(if_match, exp)
        if precondition is not None:
            return precondition
        try:
            assets.upsert(exp, entry, creating=False)
        except assets.UnsupportedAsset as refusal:  # pragma: no cover - not reachable
            return _asset_refusal(refusal)
        # EVERY RUN HOLDING THIS ASSET IS REWRITTEN FROM THE LIBRARY, even when the
        # associations themselves are untouched (`run_ids is None`). That rewrite is
        # what makes the library and the run copies one fact: an edited digest can
        # never be left stale on a run that already cited it.
        assets.set_associations(exp, entry, run_ids)
        _changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another writer won the race; nothing was changed
        response.headers["ETag"] = exp.etag()
        return {
            "asset": _asset_view(exp, entry),
            "experiment_version": exp.version_token(),
        }


@router.post(
    "/experiments/{experiment_id}/assets/{asset_id}/remove",
    tags=[TAG_EXPERIMENTS],
    summary="Remove an Asset Reference",
    description=_ASSETS_REMOVE_DESCRIPTION,
    response_description=(
        "What was removed and the record's new revision, with the record's new "
        "`ETag`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_ASSET_NOT_FOUND, **_R_PRECONDITION},
)
def post_asset_remove(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    asset_id: AssetId,
    response: Response,
    body: dict = Body(
        ...,
        description="`{\"confirmed_by_user\": true}`. Nothing else is read.",
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The RECORD's current `ETag`, exactly as a read operation "
            "returned it."
        ),
    ),
):
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        if assets.find(exp.draft, asset_id) is None:
            return _asset_not_found(experiment_id, asset_id)
        if not isinstance(body, dict) or body.get("confirmed_by_user") is not True:
            return _confirmation_required("remove an asset reference")
        try:
            assets.refuse_unreadable_containers(exp)
        except assets.UnsupportedAsset as refusal:
            return _asset_refusal(refusal)
        precondition = _check_if_match(if_match, exp)
        if precondition is not None:
            return precondition
        detached = assets.associated_run_ids(exp, asset_id)
        assets.detach_everywhere(exp, asset_id)
        assets.remove(exp, asset_id)
        _changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another writer won the race; nothing was removed
        response.headers["ETag"] = exp.etag()
        return {
            "removed_asset_id": asset_id,
            # NAMED, NOT COUNTED. A removal that also detached the asset from three
            # runs changed three runs, and a client that is told only "removed" cannot
            # tell its reader which measurements stopped citing the file.
            "detached_from_runs": detached,
            "experiment_version": exp.version_token(),
        }


# --- 8. export ----------------------------------------------------------------


def _write_record(exp: Experiment, result, unit=None, *, uploaded_by=None) -> dict:
    """Write ONE unit's record + sidecar into the records dir and mark it exported.

    ``uploaded_by`` is the SERVER-OWNED attribution stamp, and it arrives here as an
    already-resolved subject rather than as an identity, so that the only thing this
    function can do with it is write it. It is ``None`` on every deployment this build
    ships — see :mod:`isaac_api.record_attribution` for why that is the finished
    behaviour and not a gap. The stamp is applied to a COPY, after the truth core has
    produced ``result.record`` and stripped the field: ``result.record`` itself is read
    again by this function (for the record id) and by the caller, and must not gain a
    field those readers did not ask for.

    ``unit`` is an :class:`~isaac_api.workspace.ExportUnit`. It defaults to ``None``
    for the pre-fan-out shape — one experiment, one record, ``exp.record_id`` — which
    is what the test suite's fault-injection helpers drive, and what an experiment
    with no runs still does. With a unit, the record id lands on the unit's Run
    instead (contract §1 D1: the record identity is per-Run).

    The filenames come from ``result.record["record_id"]``, which is what
    ``export_draft`` minted, NOT from the unit — so the file and the id inside it can
    never disagree.

    ONE INVARIANT IS NARROWED BY THE STAMP, AND IT IS SAID HERE RATHER THAN LEFT TO BE
    DISCOVERED. ``export_draft`` validated ``result.record``; this writes a DIFFERENT
    document. "What is on disk passed official validation" is therefore no longer
    literally true. No schema violation is reachable today — ``uploaded_by`` is an
    unconstrained ``{"type": "string"}`` and ``identity.HumanActor`` refuses an empty or
    non-string subject — and ``test_record_attribution`` validates the STAMPED bytes to
    keep that checked rather than argued. A future stamp whose value is not a plain
    string would have to re-validate here.
    """
    exp.records_dir.mkdir(parents=True, exist_ok=True)
    record_id = result.record["record_id"]
    if unit is not None:
        unit.mark_exported(record_id)
    else:
        exp.record_id = record_id
    record_path = exp.records_dir / f"{record_id}.json"
    sidecar_path = exp.records_dir / f"{record_id}.evidence.json"
    written_record = record_attribution.with_server_stamp(result.record, uploaded_by)
    atomic_write_text(record_path, json.dumps(written_record, indent=2) + "\n")
    atomic_write_text(sidecar_path, json.dumps(result.sidecar, indent=2) + "\n")
    # RETURNED so the response can report the bytes that reached the disk. Without it
    # the export operation described `result.record` — the unstamped truth-core output —
    # while `/artifacts`, read a moment later, reported the stamped document. An
    # operation's own account of what it wrote must match what it wrote.
    return written_record


def _artifact_stem(name: str) -> str | None:
    """``<record-id>`` for one artifact filename, or ``None`` if it is not one.

    ONE definition, shared by the prune's candidate scan and its link-target scan, so
    the set of files it may delete and the set it reads to protect them cannot drift.
    """
    if name.endswith(".evidence.json"):
        stem = name[: -len(".evidence.json")]
    elif name.endswith(".json"):
        stem = name[: -len(".json")]
    else:
        return None
    return stem if is_record_id(stem) else None


class _UnreadableSurvivor(Exception):
    """A record the prune would keep could not be read, so its targets are unknown."""


def _link_targets_of_surviving_records(exp: Experiment, keep_ids: set[str]) -> set[str]:
    """Every ``links[].target`` named by a record this prune is going to KEEP.

    REVIEW ITEM C4. Pruning used to be able to delete a record that a SURVIVING,
    immutable record still pointed at: delete a Run whose record a sibling links to,
    export again, and the sibling was left with a ``links[].target`` naming a file
    that no longer exists. ``dangling_link_count`` is a tracked integrity metric in
    this project, and this was the application manufacturing one.

    **Of the two available fixes, this is the one chosen.** The alternative — "do not
    emit links to units that can be pruned" — cannot be implemented honestly, because
    every run can be deleted later, so it reduces to emitting no links at all and
    deleting a relation the records support. Reading the survivors costs one JSON
    parse per kept record on the one path that deletes files, and it makes the
    protection a fact about what is on disk rather than a prediction about what a
    user will do next.

    Fail-closed by construction: an unreadable or non-JSON survivor contributes
    nothing here, but it is a KEPT file, so the only thing at stake is whether its
    targets are protected — and a survivor we cannot read is exactly when we should
    not be deleting things it may reference. Its targets are therefore treated as
    unknown, and :func:`_prune_orphan_artifacts` refuses to prune at all in that case
    (see ``unreadable``).
    """
    targets: set[str] = set()
    records_dir = exp.records_dir
    for path in sorted(records_dir.iterdir()):
        if not path.is_file() or not path.name.endswith(".json"):
            continue
        if path.name.endswith(".evidence.json"):
            continue
        stem = _artifact_stem(path.name)
        if stem is None or stem not in keep_ids:
            continue
        record = _read_artifact_json(path)
        if record is None:
            raise _UnreadableSurvivor(stem)
        for link in record.get("links") or []:
            if isinstance(link, dict) and isinstance(link.get("target"), str):
                targets.add(link["target"])
    return targets


def _prune_orphan_artifacts(exp: Experiment, keep_ids: set[str]) -> dict:
    """Remove artifact pairs in this experiment's records dir that nothing points at.

    Returns ``{"pruned": [...], "protected": [...], "declined": bool}`` — see the two
    review items at the end of this docstring for why one list was not enough.

    WHY THIS EXISTS. A fan-out writes one pair per Run. Delete a Run, then export
    again *for some other reason* — a newly added run, a run not yet exported — and
    the deleted run's pair is still on disk, named by an id no state references: an
    orphan that ``get_artifacts`` cannot reach, that no reset bucket classifies, and
    that any future artifact listing would present as a record of this experiment.

    **HOW OFTEN IT ACTUALLY REMOVES ANYTHING, MEASURED (review item F3).** The
    sentence above describes the intent; this one describes the behaviour, and they
    are further apart than the first revision of this docstring admitted. The C4
    protection below keeps any stem named as a ``links[].target`` by a KEPT record —
    and sibling records are MUTUALLY linked whenever two or more runs resolve to the
    same ``sample.sample_id``, which is the intended normal case, not an edge one.
    Surviving records are immutable, so that protection never expires. Measured::

        2 runs sharing sample_id, exported (mutually linked);
        delete run 2, add run 3, export ->
          pruned_record_ids: []
          stems on disk: [run 1, run 2 (orphan), run 3]

    The orphan accumulates, permanently, in the ordinary case. That trade is KEPT —
    deleting a record a surviving immutable record still points at manufactures a
    dangling link, and an accumulated orphan is recoverable where a deleted record is
    not — but it is no longer silent: ``protected`` names every stem the prune
    declined to remove for this reason, so the accumulation is visible in the response
    instead of being inferable only by listing the directory.

    The headline coverage for the removal path
    (``test_re_export_after_a_run_is_removed_leaves_no_orphan_artifact``) passes only
    because its fixture uses ``sample_id=None`` and therefore emits no links at all;
    ``test_a_shared_sample_id_makes_the_prune_decline_and_the_response_say_so`` is the
    companion that exercises the case a user will actually hit.

    **WHAT IT DOES NOT DO, corrected (review item C8).** An earlier version of this
    docstring said the cleanup exists so that *"Delete a Run and export again and its
    pair is still on disk … Re-export must not accumulate those"*. That describes a
    capability the caller cannot invoke: an export with NO pending unit returns 409
    from the immutability guard and never reaches this function, so deleting the LAST
    unexported run — or deleting a run from a fully-exported fan-out — leaves its pair
    on disk permanently. The prune runs only on the success path of an export that
    wrote at least one unit.

    **That limit is deliberate rather than merely unfixed.** Reaching the cleanup from
    the 409 path would make a filesystem DELETION possible on a request that changes
    no state, and ``workspace``'s reset-precondition note relies on the opposite: the
    per-record plan-digest row can only miss a filesystem change that happens on a
    path which also moves the row. A delete on the 409 path would be invisible to the
    reset precondition, which is the class of defect PR #91 was written to remove. So
    the orphan is left, and this docstring says so, rather than a comfortable claim
    being left in place.

    FIVE THINGS BOUND WHAT IT CAN DELETE, because this is the only code in the
    application that removes an exported artifact:

    * it only ever looks inside ``exp.records_dir``, which belongs to this one
      experiment;
    * only a regular file named exactly ``<record-id>.json`` or
      ``<record-id>.evidence.json`` is a candidate — ``is_record_id`` on the stem, so
      a file with any other name is never touched;
    * ``keep_ids`` is assembled by the caller and holds every current unit's target
      id, every current unit's ``record_id``, and ``exp.id`` itself — see the call
      site for why the last two are there (review items C3 and C7);
    * a stem named by ``links[].target`` in any record being kept is never pruned
      (review item C4, :func:`_link_targets_of_surviving_records`);
    * the CALLER only invokes it for an experiment that HAS runs. A zero-run
      experiment's export path is byte-for-byte what it was, pruning included — which
      is to say, not included.

    **Every removal is logged at WARNING (review item C3b).** This is the only
    destructive operation in the application and it used to be the quietest one: the
    strictly less consequential export reconciliation, which deletes nothing, logs.
    Path-free by rule (P30.6) — the record id and the basename only.

    ``pruned`` is the ids removed, MEASURED from the unlinks that succeeded rather
    than asserted from what was planned, so the response can disclose them. A failed
    unlink is skipped rather than raised: this runs after the artifacts were written
    and the export succeeded, and turning a tidy-up failure into a 500 would report a
    successful export as a failure.

    **``declined`` EXISTS BECAUSE THIS FUNCTION NOW HAS TWO INDEPENDENT WAYS OF DOING
    NOTHING (review item F9).** One unreadable kept record disables pruning entirely
    (fail-closed, below); with the F3 disclosure above there is a second no-op path,
    and an empty ``pruned`` therefore meant three different things — nothing was
    orphaned, everything orphaned was protected, or nothing was even examined. The
    caller can now tell them apart, which matters most for the third: a declined prune
    is the one that reports a state an operator should look at.
    """
    records_dir = exp.records_dir
    if not records_dir.is_dir():
        return {"pruned": [], "protected": [], "declined": False}
    try:
        link_targets = _link_targets_of_surviving_records(exp, keep_ids)
    except _UnreadableSurvivor as unreadable:
        # A record we are keeping could not be read, so we do not know what it
        # points at. Delete nothing: an accumulated orphan is recoverable, a record
        # deleted out from under a live link is not.
        _log.warning(
            "export prune: skipped entirely because kept record %s could not be read, "
            "so its link targets are unknown",
            unreadable.args[0],
        )
        return {"pruned": [], "protected": [], "declined": True}
    protected = keep_ids | link_targets
    removed: set[str] = set()
    spared: set[str] = set()
    for path in sorted(records_dir.iterdir()):
        if not path.is_file():
            continue
        stem = _artifact_stem(path.name)
        if stem is None:
            continue
        if stem in protected:
            # Only a stem NO CURRENT UNIT CLAIMS is reported as protected. A stem in
            # `keep_ids` is a live record of this experiment, not an orphan that
            # survived — reporting those would bury the one fact this list exists to
            # publish under a restatement of the run set.
            if stem not in keep_ids:
                spared.add(stem)
            continue
        try:
            path.unlink()
        except OSError:
            continue
        if stem not in removed:
            _log.warning(
                "export prune: removed the artifact pair for record %s from "
                "experiment %s; no current run claims that id",
                stem,
                exp.id,
            )
        removed.add(stem)
    if spared:
        _log.warning(
            "export prune: kept %d orphan artifact pair(s) in experiment %s that no "
            "current run claims, because a surviving record still links to them",
            len(spared),
            exp.id,
        )
    return {
        "pruned": sorted(removed),
        "protected": sorted(spared),
        "declined": False,
    }


def _flat_export_errors(payload: dict, result) -> list:
    """The flat `errors` list this endpoint has always returned for a failed export.

    Extracted verbatim from the handler so the fan-out branch and the single-record
    branch cannot drift: official errors when the record was built and refused,
    otherwise the draft errors that stopped it being built at all.
    """
    if payload["official_report"]:
        return payload["official_report"]["errors"]
    if not result.draft_report.ok:
        return payload["draft_report"]["errors"]
    return []


def _unit_result_entry(unit, result) -> dict:
    """One unit's verdict, ADDRESSED TO ITS RUN.

    "Per-run failures must be addressable to the correct Run" is not satisfied by a
    flat error list: three runs can produce the same message and a client cannot tell
    which to open. So every entry names its run and carries that run's own reports.
    """
    payload = serialize.export_result_to_dict(result)
    return {
        "run_id": unit.run_id,
        "run_label": unit.run_label,
        "record_id": unit.target_id,
        "ok": result.ok,
        "errors": _flat_export_errors(payload, result),
        "draft_report": payload["draft_report"],
        "official_report": payload["official_report"],
    }


def _unit_artifact_entry(unit: ws.ExportUnit) -> dict:
    """One successfully written unit: which run, which record, which two files.

    P30.6 — SAFE basenames only, never a filesystem path. The id is read back from
    the unit AFTER `_write_record` marked it, so it is the id actually written.
    """
    record_path = unit.record_path()
    sidecar_path = unit.sidecar_path()
    return {
        "run_id": unit.run_id,
        "run_label": unit.run_label,
        "record_id": unit.current_record_id(),
        "record_filename": record_path.name if record_path is not None else None,
        "sidecar_filename": sidecar_path.name if sidecar_path is not None else None,
    }


@dataclasses.dataclass
class _Materialisation:
    """What one pass of "turn every pending unit into its artifact pair" produced.

    EXTRACTED FROM ``post_export`` SO ``post_submit`` CAN REUSE IT, and extracted
    rather than re-implemented for a specific reason: submit must publish exactly
    the records export publishes, from exactly the same validation gate. Two
    materialisation paths would eventually disagree about which units are eligible,
    what a failure means, or when the state is saved — and the disagreement would
    show up as records that exist under one route and not the other.

    ``post_submit`` DOES NOT CALL THE EXPORT ROUTE, and could not. ``post_export``
    answers ``409 record_exists`` when every unit is already materialised, which is
    the normal state of a fully-exported experiment — so routing submit through it
    would make the most-ready experiments the ones that cannot be submitted.
    """

    #: ``(unit, ExportResult)`` for the units this pass attempted. Already
    #: materialised units are never in here: they are skipped by the caller and are
    #: never revalidated or rewritten, which is what keeps exported records
    #: immutable across a partial fan-out.
    results: list
    #: The subset whose export gate refused. Non-empty means NOTHING was written.
    failures: list
    #: What ``save_versioned`` reported, so a caller reports a mutation that
    #: happened rather than one it assumed.
    changed: bool
    #: A 412 to return verbatim, or ``None``. Its arrival means every artifact pair
    #: WAS written and the state save was refused — see ``_save_versioned``.
    stale: JSONResponse | None
    #: ``_prune_orphan_artifacts``' three keys, or ``None`` when no prune ran (a
    #: zero-run experiment, or a pass that wrote nothing).
    prune: dict | None
    #: Whether any artifact reached the disk during this pass.
    written: bool
    #: The document ACTUALLY WRITTEN for each unit, keyed by ``unit.target_id`` — the
    #: truth core's record plus the server-owned attribution stamp, which is what a
    #: response must report rather than the unstamped `result.record`. Empty on every
    #: path that wrote nothing.
    written_records: dict = dataclasses.field(default_factory=dict)


def _materialise_pending_units(
    exp, pending_units, if_match, *, units, uploaded_by=None
) -> _Materialisation:
    """Validate every pending unit, then write every one of them. THE COMMIT BOUNDARY.

    PHASE 1 validates EVERY eligible unit and writes nothing — ``export_draft`` is a
    pure transform plus two validations. A single failure means no artifact is
    written for ANY unit, which is contract §3 D4's rule (a required validation
    failure on any Run blocks the whole submission) and is why validation is a
    separate pass rather than interleaved with the writes.

    PHASE 2 writes each unit's pair and then saves the state ONCE. It is NOT atomic
    across the individual file writes: a fault between them leaves some records on
    disk with the state still saying they were not exported. That state is
    recoverable rather than merely tolerated — the export route's reconciliation
    branch republishes any unit that has an orphan artifact and no ``record_id`` —
    and it is documented on the export operation itself.

    The prune runs ONLY for a fan-out and ONLY after a successful state save, so a
    run removed from the experiment cannot leave its record behind.
    """
    results = [
        (unit, export_draft(unit.draft, REPO_ROOT, record_id=unit.target_id))
        for unit in pending_units
    ]
    failures = [(unit, result) for unit, result in results if not result.ok]
    if failures:
        return _Materialisation(
            results=results,
            failures=failures,
            changed=False,
            stale=None,
            prune=None,
            written=False,
        )
    written_records: dict[str, dict] = {}
    for unit, unit_result in results:
        written_records[unit.target_id] = _write_record(
            exp, unit_result, unit, uploaded_by=uploaded_by
        )
    # export normally changes the authoritative state (record_id: None -> id), so
    # this bumps rev and stamps updated_utc, persisting the state atomically. On a
    # self-heal of an already-exported record `record_id` is ALREADY set, the
    # authoritative signature is unchanged, and it returns False without rewriting
    # anything — a filesystem repair, not a scientific state change. That return
    # value is PASSED THROUGH to the caller's invalidation rather than hardcoded.
    changed, stale = _save_versioned(exp, if_match)
    if stale is not None:
        return _Materialisation(
            written_records=written_records,
            results=results,
            failures=[],
            changed=False,
            stale=stale,
            prune=None,
            written=True,
        )
    prune = None
    if exp.runs:
        # THE KEEP-SET, and both additions to it are review fixes.
        #
        # C7 — `unit.target_id` is what the keep-set was built from, but the file on
        # disk is named by `current_record_id()`. `ExportUnit.mark_exported` now
        # refuses to let those diverge, so this is belt-and-braces; it costs nothing
        # and it means the keep-set is expressed in terms of the id that actually
        # names a file, not only the id we track.
        #
        # C3 — `exp.id` unconditionally, NOT `exp.record_id`. The old rule kept
        # `exp.record_id` "so a legacy 1:1 artifact is preserved even after runs are
        # added", but `exp.record_id` is None in exactly the half-written state the
        # reconciliation branch exists to repair (the artifact pair was written, the
        # state save faulted). A run added afterwards therefore DELETED the
        # previously exported record. A stem equal to the experiment's own id is
        # never a fan-out record — record ids come from `Run.id` — so keeping it can
        # only protect a legacy pair.
        keep = {unit.target_id for unit in units}
        keep.update(
            record_id
            for record_id in (unit.current_record_id() for unit in units)
            if record_id is not None
        )
        keep.add(exp.id)
        if exp.record_id is not None:
            keep.add(exp.record_id)
        prune = _prune_orphan_artifacts(exp, keep)
    return _Materialisation(
        written_records=written_records,
        results=results,
        failures=[],
        changed=changed,
        stale=None,
        prune=prune,
        written=True,
    )


def _sibling_link_conflict(exp, units) -> JSONResponse | None:
    """The ``409 sibling_link_conflict`` refusal, or ``None``. Shared by two routes.

    C1 closed EMIT-TIME falsity: ``_linkable`` stops an export writing a link its
    target disproves. Nothing asked the converse — does REWRITING a record falsify a
    link a SURVIVING sibling already carries? Measured on ``c467dc7``: two runs share
    ``SYN-A``, are exported and mutually linked; delete run 1's artifacts, change the
    experiment's ``sample.sample_id``, export along the blessed self-heal path, and
    the surviving immutable record still asserts a shared sample id that the rewritten
    one now contradicts. There is no write that leaves both true, so the operation is
    REFUSED rather than performed with a correction we are not allowed to make.

    A zero-run experiment has no siblings, so this cannot fire for one.

    ONE REMEDY, NOT TWO (review item F-B). The message used to end "Restore the sample
    id, or remove the run." The second clause was measured end to end and it
    manufactures the defect the prune exists to prevent: removing the run leaves the
    immutable survivor's ``same_sample_as`` link naming a record that will never
    exist, and nothing reports it. Restoring the sample id is the only remedy that
    leaves both records true, so it is the only one offered.
    """
    if not exp.runs:
        return None
    conflicts = ws.sibling_link_conflicts(units)
    if not conflicts:
        return None
    _log.warning(
        "operation refused for record %s: writing %d run record(s) would "
        "falsify a same_sample_as link an already-exported sibling carries",
        exp.id,
        len({conflict["record_id"] for conflict in conflicts}),
    )
    return JSONResponse(
        status_code=409,
        content={
            "error": "sibling_link_conflict",
            "message": (
                "This export would rewrite a record that an already-"
                "exported record links to as sharing its sample id, with "
                "a different sample id. Exported records are immutable, "
                "so the link could not be corrected and one of the two "
                "records would be false. Nothing was written. Restore the "
                "sample id to match the one the exported record names."
            ),
            "conflicts": conflicts,
            # THE PUBLICATION DISCLOSURE, on a refusal that publishes nothing. The
            # submit contract promises `published_record_count` and `records` on
            # EVERY one of its 409 bodies and this one did not carry them; see
            # `_publication_disclosure` for the measurement and for why the promise
            # was restored rather than scoped down.
            #
            # IT LANDS ON THE EXPORT ROUTE TOO, because this helper is shared, and
            # that is correct rather than collateral: this check runs before either
            # route writes anything, so `0`/`[]` is exactly as true there. Adding a
            # constant-zero pair is additive for a client and cannot mislead one.
            **_NOTHING_PUBLISHED_FIELDS,
        },
    )


@router.post(
    "/experiments/{experiment_id}/export",
    tags=[TAG_EXPORT],
    summary="Export a Record to an Official ISAAC Record",
    description=(
        "Runs the schema-gated export for this record. On success it writes the "
        "official ISAAC record and its evidence sidecar into the workspace and "
        "returns the record id, the two artifact filenames (basenames only, never "
        "a server path), the refreshed revision metadata, the workflow, and the "
        "downstream invalidation.\n\n"
        "A record with **runs** exports one official record per run "
        "(`record_id = run.id`), not one per record. In that case `record_id` and "
        "`artifact_refs` are `null` — they are singular and a fan-out has several — "
        "and `records[]` carries one entry per run instead. A record with no runs — "
        "which is how every record starts, and how it stays until a run is added "
        "through `POST /api/experiments/{experiment_id}/runs` — exports exactly one "
        "record with `record_id` equal to its own id, unchanged.\n\n"
        "**What is guaranteed if something fails part-way.** Every run is validated "
        "before any file is written, so a validation failure on one run means no "
        "file is written for any of them. The state is saved once, after every "
        "file. It is NOT atomic across the individual file writes: a fault between "
        "them can leave some records on disk with the state still saying they were "
        "not exported. That is the same half-written shape a single-record export "
        "has always been able to produce, and the same repair applies — retry the "
        "export and every not-yet-exported run is republished from its current "
        "draft.\n\n"
        "A gated failure also returns `200`, with `ok: false`, the failing draft "
        "and official reports, and a flat `errors` list — decide by reading `ok`, "
        "not the status code. With runs, `runs[]` carries each run's own verdict and "
        "`failed_run_ids` names the ones that refused. Nothing is written in that "
        "case.\n\n"
        "**What happens to the records of runs that have been removed.** When a "
        "record with runs exports, artifact pairs in its own records directory that "
        "no current run claims are removed, and `pruned_record_ids` names them. Two "
        "things stop that removal, and they are reported separately because an empty "
        "`pruned_record_ids` would otherwise mean three different things. A pair a "
        "surviving record still links to is kept and named in "
        "`protected_record_ids` — records are immutable, so removing it would leave "
        "that link pointing at nothing. And if a record being kept cannot be read at "
        "all, nothing is removed and `prune_declined` is `true`, because a record "
        "whose links are unknown may reference anything.\n\n"
        "Requires the record's current `ETag` in `If-Match`. Exported records are "
        "immutable: exporting a record whose runs have all already been exported is "
        "refused, and a run that is already exported is never rewritten when a "
        "sibling run is exported alongside it. An export is also refused with "
        "`sibling_link_conflict` when it would rewrite a record that an already-"
        "exported record links to as sharing its sample id, with a different sample "
        "id — the link could not be corrected afterwards, so one of the two records "
        "would be false. Nothing is written in that case."
    ),
    response_description=(
        "The export result. `ok: true` means the record and sidecar were written; "
        "`ok: false` means the gate refused and nothing was written."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        **_R_PRECONDITION,
        # OVERRIDES the shared `_R_PRECONDITION` 412, which says "nothing was
        # written" — true of every other operation and NOT true of this one. Export
        # writes its two artifacts before it saves the state, so the second of the
        # two 412 arms leaves them on disk. Same defect class as the shared save
        # helper's docstring, one surface further out: this is the description a
        # client actually reads.
        412: {
            "description": (
                "The write was refused because another writer got there first, so "
                "your change was not applied and the response echoes the current "
                "`ETag` so a client can refresh in one further request.\n\n"
                "Two arms, and they differ in what is left on disk. If `If-Match` "
                "did not match the revision this server read, nothing at all was "
                "written. If the record's stored copy moved on between that check "
                "and the durable write, every official record and evidence sidecar "
                "this export produced had ALREADY been written and they remain — "
                "the record's own state was not updated, so it still reports as not "
                "exported. That is a state this API repairs by itself: retry the "
                "export and it republishes from the current draft, for every run "
                "that is not yet exported."
            )
        },
        409: {
            "description": (
                "This record has already been exported. Records are immutable, so "
                "nothing was overwritten."
            )
        },
    },
)
def post_export(
    request: Request,
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The record's current `ETag`, exactly as a read operation "
            "returned it."
        ),
    ),
):
    # Cheap existence pre-check OUTSIDE the lock so a bogus/non-existent id never
    # creates a permanent entry in the never-evicting per-record lock map.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    # The per-record lock serialises load->precondition->mutate->save; load FRESH
    # inside the lock. The precondition (400/412) is evaluated BEFORE the export
    # immutability 409 so a stale client refreshes before making a state decision.
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window

        err = _check_if_match(if_match, exp)
        if err is not None:
            return err

        # Capture the PRE-export workflow for the reopen DELTA (export normally
        # completes the final step, so no step reopens — but we report honestly).
        pre_steps = _workflow_for(exp)["ordered_steps"]

        # Immutability guard (mirrors cli.cmd_export): never overwrite the record of
        # an ALREADY-EXPORTED experiment whose artifacts are BOTH on disk.
        #
        # The guard is deliberately STATE-aware, not file-only. The 409 this returns
        # makes a STATE claim ("This record has already been exported") — see the
        # `responses` entry above — and a file on disk is only a valid proxy for that
        # claim while state and disk AGREE. They can disagree: this handler writes
        # artifact -> sidecar -> state (`_write_record`, then `save_versioned`), so a
        # fault anywhere in that window leaves the artifact(s) on disk with
        # `record_id` still null. A file-only guard then WEDGED the record: every
        # clean retry returned 409 forever, the wedge survived a restart (it is all
        # on disk), and with no per-record repair route the only recovery was the
        # destructive whole-workspace reset. So an orphan artifact is reconciled
        # (below) instead of being mistaken for an exported record. Covered by
        # `apps/api/tests/test_export_recovery.py`, which pins every state x file
        # combination: rows 1-4 for the record file, plus rows 3b/3c for each half of
        # the pair.
        #
        # BOTH files are required, not just the record. An export produces a PAIR,
        # and the sidecar is written second, so `record present + sidecar absent` is
        # a reachable half-written state — reachable from the very self-heal this
        # slice blesses (fault the sidecar write during the exported+missing repair).
        # With a record-only check that state was a PERMANENT 409 wedge whose sidecar
        # could never be regenerated: the exact defect class this guard was fixed to
        # remove, one file over. Requiring both is also the SAME rule `get_artifacts`
        # already applies ("force `stale` whenever EITHER file failed to read"), so
        # the two agree about what "the artifact is present" means.
        #
        # THE GUARD IS NOW PER UNIT (contract §1 D1 — one Run, one record). For an
        # experiment with NO runs there is exactly one unit whose target id is
        # `exp.id` and whose `current_record_id()` is `exp.record_id`, so
        # `unit.materialised()` is character-for-character the old
        # `exp.exported() and record_path.exists() and sidecar_path.exists()`. The
        # 409 body below is likewise built from that unit, so a zero-run experiment's
        # refusal is byte-identical to the one this endpoint has always returned.
        units = exp.export_units()
        pending_units = [unit for unit in units if not unit.materialised()]
        if not pending_units:
            # Every unit is already exported AND both halves of its pair are on disk.
            #
            # REVIEW ITEM C10. This used to fill the singular `record_id` from
            # `units[0]` for a fan-out too, which contradicted this endpoint's own
            # documentation ("`record_id` … `null` — they are singular and a fan-out
            # has several") and named one arbitrary run's record as though it were
            # THE record. For a fan-out the id is null and the message counts instead
            # of naming. For a zero-run experiment — which is how every experiment
            # starts, and how it stays until `POST .../runs` adds one — the body is
            # byte-identical to the one it has always returned.
            if exp.runs:
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": "record_exists",
                        "message": (
                            f"All {len(units)} records for this record's runs have "
                            "already been exported; records are immutable."
                        ),
                        "record_id": None,
                    },
                )
            first = units[0]
            first_record = first.record_path()
            name = first_record.name if first_record is not None else f"{first.target_id}.json"
            return JSONResponse(
                status_code=409,
                content={
                    "error": "record_exists",
                    "message": f"{name} already exists; records are immutable.",
                    "record_id": first.target_id,
                },
            )

        # A unit that IS materialised is skipped entirely from here on — never
        # revalidated, never rewritten. That is what keeps records immutable during a
        # PARTIAL fan-out: adding a sixth run to an experiment whose five records are
        # already on disk exports the sixth and leaves the five untouched, rather than
        # republishing them from a draft that may have moved on since.
        for unit in pending_units:
            record_path = unit.record_path()
            if unit.current_record_id() is None and record_path is not None and record_path.exists():
                # RECONCILIATION: not exported, yet an artifact exists — the crash
                # window above. Proceed and republish from the CURRENT draft (the
                # orphan may be a projection of an older draft, so it is replaced,
                # never adopted). Warn so an operator sees that a fault happened
                # rather than the repair being silent. Path-free by rule: the record
                # id and the BASENAME only, never a filesystem path (P30.6, and a log
                # line is an exfiltration surface too).
                #
                # The `current_record_id() is None` test is EXPLICIT (it was implied
                # by the fall-through before the sidecar clause above existed). This
                # warning means exactly one thing — "state and disk disagree about
                # whether an export happened" — and an exported record missing one of
                # its files is NOT that: state and disk agree an export happened, one
                # file is simply gone. That is the same class as the mirror case,
                # which is deliberately silent (see
                # `test_no_reconciliation_warning_on_the_mirror_case`), so both
                # self-heals stay silent and the warning keeps one unambiguous
                # meaning.
                _log.warning(
                    "export reconciliation: record %s has an orphan artifact %s on disk "
                    "while its state says not exported (a fault between the artifact "
                    "write and the state save); republishing from the current draft",
                    unit.target_id,
                    record_path.name,
                )

        # ---- REWRITE-TIME FALSITY (review item F7), CHECKED BEFORE ANYTHING RUNS ---
        #
        # The whole argument, the measurement behind it and the one-remedy decision
        # now live at `_sibling_link_conflict`, which `post_submit` shares. It is one
        # refusal with one wording; two copies would eventually be two wordings.
        #
        # A zero-run experiment has no siblings, so this cannot fire for one. That
        # used to read "…for any experiment this API can currently create", which
        # stopped being true the moment `POST .../runs` shipped: a client can add
        # runs to a record it created, so this branch IS reachable over HTTP.
        conflict = _sibling_link_conflict(exp, units)
        if conflict is not None:
            return conflict

        # ---- THE COMMIT BOUNDARY, stated exactly (see the endpoint description) ----
        # Extracted to `_materialise_pending_units` so `post_submit` publishes exactly
        # the records this route publishes, through exactly the same gate. The two
        # phases and what each guarantees are documented there.
        # The server-owned `attribution.uploaded_by` stamp. NOT
        # `require_human_actor`: unlike submission, exporting is a mechanical
        # transform that has never required an actor, the schema does not mark the
        # field required, and refusing an export because the deployment cannot name
        # an uploader would remove a working capability in exchange for an optional
        # field. Fail-open on availability, fail-closed on attribution — the export
        # always proceeds and the field appears only when a verifier vouched for a
        # name, which no deployment shipped today does.
        materialisation = _materialise_pending_units(
            exp, pending_units, if_match, units=units,
            uploaded_by=record_attribution.resolve_uploaded_by(
                identity_module.resolve_identity_for_request(request), scope
            ),
        )
        results = materialisation.results
        failures = materialisation.failures
        if failures:
            # Nothing written. Surface the failing reports and a flat errors list.
            # No mutation happened, so report an honest changed=False invalidation
            # (never fabricate a mutation that did not occur).
            #
            # The top-level report is the FIRST FAILING unit's, not the first unit's:
            # a client that reads only `errors` must be shown an actual failure. Every
            # unit's own verdict is in `runs`, so nothing is hidden by that choice.
            first_failed = failures[0][1]
            payload = serialize.export_result_to_dict(first_failed)
            payload["errors"] = _flat_export_errors(payload, first_failed)
            if exp.runs:
                payload.pop("record", None)
                payload.pop("sidecar", None)
                payload["runs"] = [
                    _unit_result_entry(unit, result) for unit, result in results
                ]
                payload["failed_run_ids"] = [unit.run_id for unit, _ in failures]
            payload["workflow"] = _workflow_for(exp)
            payload["invalidation"] = dependencies.build_invalidation(
                changed=False, changed_fields=[], pre_steps=pre_steps, post_exp=exp
            )
            return JSONResponse(status_code=200, content=payload)

        # PHASE 2 ran inside `_materialise_pending_units`. See the endpoint's 412
        # description and that helper for what a fault BETWEEN two units' writes
        # leaves behind, and why that state is recoverable rather than merely
        # tolerated.
        if materialisation.stale is not None:
            # EVERY unit's artifact PAIR was already written to disk and the state
            # was not — the same half-written shape a fault between the two produces,
            # and the one this handler's own reconciliation branch repairs on the
            # next export (a unit with no `record_id` + an orphan artifact ->
            # republish from the current draft). So this degrades into a state the app
            # already handles rather than into a new one. With N units it is N orphan
            # pairs instead of one, repaired by the same loop.
            return materialisation.stale
        changed = materialisation.changed
        result = results[0][1]
        # The document that reached the DISK, not the truth core's unstamped output.
        # See `serialize.export_result_to_dict`'s `record` override for why.
        payload = serialize.export_result_to_dict(
            result, record=materialisation.written_records.get(results[0][0].target_id)
        )
        if exp.runs:
            # Orphan pruning ran ONLY for a fan-out and ONLY after a successful state
            # save, so a run removed from the experiment cannot leave its record
            # behind. See `_prune_orphan_artifacts` for the four bounds on what it may
            # delete, and `_materialise_pending_units` for the keep-set.
            prune = materialisation.prune or {"pruned": [], "protected": [], "declined": False}
            # FAN-OUT SHAPE. `record_id` / `artifact_refs` are SINGULAR by name and by
            # every existing client's reading of them, and a fan-out has N of each.
            # Filling them from an arbitrary one of the N would be a false singular,
            # so they are null and `records` carries the truth.
            #
            # `records` lists what THIS export produced, not every record the
            # experiment owns — on a partial fan-out the already-materialised units
            # were skipped and are deliberately absent, because reporting them here
            # would claim writes that did not happen. This used to add "nothing that
            # exists today can reach this branch (no route creates a Run), so no
            # client contract is being changed" — FALSE since `POST .../runs`
            # shipped. The branch is reachable, and the shape above is the contract
            # a fan-out client reads; it is described in this operation's own
            # OpenAPI description rather than resting on unreachability.
            payload.pop("record", None)
            payload.pop("sidecar", None)
            payload["record_id"] = None
            payload["artifact_refs"] = None
            payload["records"] = [_unit_artifact_entry(unit) for unit, _ in results]
            # THREE KEYS, NOT ONE (review items F3 and F9). `pruned_record_ids` alone
            # could not distinguish "nothing was orphaned" from "every orphan is
            # protected by a surviving record's link" from "one kept record could not
            # be read, so nothing was even examined" — and the middle case is the
            # NORMAL one for a fan-out whose runs share a sample id. See
            # `_prune_orphan_artifacts`.
            #
            # AND ALL THREE ARE VISIBLE ONLY HERE (review item F-F, recorded not
            # fixed). They are fields of an EXPORT RESPONSE, so the accumulation they
            # describe is reported only to whoever performed the export that noticed
            # it. Delete a run from a fully-exported fan-out and never export again
            # and no surface reports the orphan at all: `/artifacts` serves the
            # experiment's own pair, `artifact_state` iterates the CURRENT units and
            # so cannot see a file no unit claims, and `/audit` globs the records dir
            # and would report the orphan as a passing record rather than as an
            # orphan. A standing signal belongs on a read surface — the Run-workspace
            # slice, which is the one with somewhere to put it.
            payload["pruned_record_ids"] = prune["pruned"]
            payload["protected_record_ids"] = prune["protected"]
            payload["prune_declined"] = prune["declined"]
        else:
            payload["record_id"] = exp.record_id
            # P30.6 — SAFE basename only (see _detail); never the absolute path.
            payload["artifact_refs"] = {
                "record_filename": exp.record_path().name,
                "sidecar_filename": exp.sidecar_path().name,
            }
        payload.update(vc.version_fields(exp))
        # export completes the final workflow step and makes the artifact current.
        payload["workflow"] = _workflow_for(exp)
        payload["invalidation"] = dependencies.build_invalidation(
            changed=changed,
            changed_fields=["record_id"] if changed else [],
            pre_steps=pre_steps,
            post_exp=exp,
        )
        response.headers["ETag"] = exp.etag()
        return payload


# --- 8a-bis. SUBMISSION -------------------------------------------------------
#
# SUBMIT IS NOT EXPORT, AND NOTHING HERE MAY DERIVE ONE FROM THE OTHER.
#
# Export is a mechanical transform that answers "does this validate". Submission is
# a DECLARATION BY A PERSON — "this experiment is finished, and I am the one saying
# so" — and it answers "who finalised this, when, over exactly what content". An
# export can be performed by any caller at any time, so treating an exported record
# as submitted would attribute a declaration nobody made. `test_submission.py` pins
# that in the one direction that matters: exporting sets no submission state.
#
# The submission and its revision snapshot live in the database (`0003_revisions`,
# `0004_submissions`) and CANNOT live in the experiment document. Two mechanical
# reasons, both measured, both written out at the top of `0003_revisions.sql`:
# `Q_UPSERT_EXPERIMENT` refuses a CHANGED document at the SAME rev, and
# `save_versioned` does not attempt a write unless `_authoritative_signature` moved,
# which covers only `{title, source, draft, record_id, runs}`.


def _publication_disclosure(published: Sequence[dict] | None) -> tuple[str, dict]:
    """What THIS REQUEST published, as a sentence and as two response fields.

    **C1 — EVERY SUBMISSION REFUSAL USED TO SAY "NOTHING WAS WRITTEN"
    UNCONDITIONALLY, AND AFTER MATERIALISATION THAT IS THE OPPOSITE OF THE TRUTH.**
    ``post_submit`` writes the official ISAAC records and saves the experiment
    state BEFORE it opens the submission transaction (the order is deliberate and is
    argued at the call site: it is the only recoverable one). So the refusals raised
    from the write — ``tables_absent``, ``database_unavailable``,
    ``already_submitted``, ``idempotency_key_conflict`` and the generic
    ``submission_conflict`` — could fire with two artifact files on disk,
    ``record_id`` set and ``rev`` moved, while telling the scientist that nothing had
    been published.

    THIS SENTENCE USED TO SAY "FOUR REFUSALS" AND LIST FOUR, and the tally was one
    short: ``database_unavailable`` is raised from the write's own ``except
    db_write.WriteRefused`` handler and is exactly as post-materialisation as
    ``tables_absent`` beside it, which the served ``503`` description also omitted.
    The numeral is gone rather than corrected — the enumeration is the claim, and it
    is pinned against the emitting code by
    ``apps/api/tests/test_submit_refusal_partition.py`` rather than by counting here.

    That is not a cosmetic inaccuracy. Exported records are IMMUTABLE and no route
    republishes one, so a scientist who believes nothing was published will edit the
    record and retry — and the retry publishes nothing, leaving the artifacts
    permanently holding the pre-edit science under ids the submission then names.

    **THE TRUE HALF IS NOT WEAKENED.** No submission row exists, and both branches
    say so. What changes is that the published half is now told as well, with the
    record ids, so the scientist can act on it.

    THE DATABASE SENTENCE IS DELIBERATELY THE WEAKER "nothing was committed" RATHER
    THAN "the transaction issued only reads", and the first draft of this helper got
    that wrong. "Only reads" is true of the tables-missing and already-recorded
    paths, where the refusal is raised before any ``INSERT``. It is FALSE of a lost
    race: by then the revision row, its run revisions and its change rows have all
    been inserted, and what saves the caller is that ``write_transaction`` rolls the
    whole thing back — not that nothing was attempted. It is also false of a
    connection that never opened, where there was no transaction to speak of. One
    sentence has to cover all three, so it claims only what all three support.

    Returns ``(sentence, fields)``. ``fields`` carries ``published_record_count`` and
    ``records``, exactly as the ``200`` carries them, so a client never has to branch
    on the status code to learn what reached the disk.

    ~~"on every refusal"~~ **— THAT WAS FALSE WHEN IT WAS WRITTEN, and it is struck
    rather than edited because the sentence it appeared in is the served contract's
    own promise.** This helper is consulted only by the refusals raised from or after
    the write. Measured over HTTP: ``human_actor_required`` came back with keys
    ``['error', 'message', 'operation', 'reason', 'trust']`` and
    ``tutorial_scope_forbidden`` with ``['error', 'header', 'message', 'operation']``
    — neither carrying either field — while the ``409`` description promised both "on
    EVERY one of these bodies". Four of the seven ``409``s lacked them:
    ``tutorial_scope_forbidden``, BOTH ``submission_blocked`` emissions,
    ``sibling_link_conflict``, and ``human_actor_required``.

    **THE FIX RESTORES THE PROMISE RATHER THAN RETREATING IT, AND THE CHOICE IS
    ARGUED.** Scoping the sentence to "the refusals that carry it" would have been the
    smaller edit, and it would have left a client branching on ``error`` before it
    knew whether it was allowed to read ``published_record_count`` — which is the
    exact thing the field exists to spare it. So the refusals this module emits itself
    now splat :data:`_NOTHING_PUBLISHED_FIELDS`, and every one of them carries the
    two keys with the constant ``0``/``[]`` that is true of them.

    **``human_actor_required`` IS THE ONE EXCEPTION, AND IT IS SCOPED RATHER THAN
    OVERLOOKED.** It is raised by ``identity.require_human_actor`` — a DEPENDENCY,
    shared with any future operation, whose payload is built in ``identity.py`` and
    knows nothing about publication; giving it these two keys would put a claim about
    THIS operation into a refusal shape that is not this operation's. FastAPI resolves
    it before the handler body runs, so nothing can have been published when it fires,
    and a client reading ``body.get("published_record_count", 0)`` is correct there.
    The served description names it by ``error``, which is the one thing a client can
    branch on without guessing.
    """
    entries = list(published or [])
    if not entries:
        return (
            "Nothing was written, and no official record was published.",
            {"published_record_count": 0, "records": []},
        )
    ids = [entry["record_id"] for entry in entries if entry.get("record_id")]
    plural = "" if len(entries) == 1 else "s"
    named = ", ".join(ids) if ids else "see `records`"
    return (
        "No submission was recorded, and nothing this request attempted in the "
        f"database was committed — but it had ALREADY published {len(entries)} "
        f"official ISAAC record{plural} before it was refused: {named}. Exported "
        "records are immutable and no operation republishes one, so those artifacts "
        "remain on disk exactly as written. If you edit this record before "
        "retrying, the published files will still hold the content submitted here.",
        {"published_record_count": len(entries), "records": entries},
    )


#: The publication disclosure for a refusal that CANNOT have published anything.
#:
#: DERIVED FROM :func:`_publication_disclosure` RATHER THAN WRITTEN OUT, so the two
#: key names cannot drift apart — a second literal copy is exactly how the served
#: partition drifted from the bodies in the first place.
#:
#: Only the FIELDS are taken, never the sentence: each body that splats this already
#: ends its own ``message`` with "Nothing was written.", and appending a second "and
#: no official record was published" would restate it in the helper's words rather
#: than the refusal's.
#:
#: THE SPLAT IS A NAMED CONSTANT AND NOT AN INLINE DICT, because
#: ``test_submit_refusal_partition.py`` reads the partition off the AST: a splat of
#: THIS name means "carries the disclosure, and cannot have published", while a splat
#: of a local ``fields`` means "carries the disclosure, and may have published". Two
#: different facts that a bare ``**{...}`` could not tell apart, and the second is the
#: one the whole partition exists to state.
_NOTHING_PUBLISHED_FIELDS: dict = _publication_disclosure(None)[1]


def _submission_unavailable(
    reason: str, lead: str, published: Sequence[dict] | None = None
) -> JSONResponse:
    """The typed ``503`` for "this deployment cannot record a submission".

    503 RATHER THAN 501 OR 409, and the choice is the same one
    ``storage_unavailable_handler`` argues. The request is well formed and the
    application is working; a dependency this deployment is configured to use is not
    ready. Every reason this can carry is resolved by an operator action that is
    already specified — configuring a database, applying a migration that is already
    committed and reviewed, or restoring one that stopped answering — so "try again
    later" is true rather than consoling.

    It is deliberately NOT the ``human_actor_required`` 409, which is a different
    fact about a different missing thing and would send an operator to the wrong
    place. And it is deliberately not the generic ``experiment_storage_unavailable``
    body: that one is raised by the EXPERIMENT write path, and this one is about the
    submission tables specifically.

    ``lead`` is the reason; the publication disclosure is appended by
    :func:`_publication_disclosure`, because ``tables_absent`` is reachable from two
    places — before anything is materialised, and after everything is.
    """
    note, fields = _publication_disclosure(published)
    return JSONResponse(
        status_code=503,
        content={
            "error": "submission_unavailable",
            "reason": reason,
            "message": f"{lead} {note}",
            **fields,
        },
    )


#: The reasons above, as prose, WITHOUT a claim about what was written. Each is
#: completed by :func:`_publication_disclosure`, which is the one place in this
#: module that decides whether "nothing was published" is a true sentence — because
#: for two of these three it depends on where the refusal was raised from.
_SUBMISSION_NO_STORAGE_LEAD = (
    "Submitting records a durable, attributable declaration, and this deployment is "
    "not configured with an application database to record one in — anything "
    "written here would be lost when the server restarts."
)
_SUBMISSION_NO_TABLES_LEAD = (
    "Submitting records a durable, attributable declaration, and this deployment's "
    "database does not yet have the tables to record it in. The migration that "
    "creates them has to be applied by an operator."
)
_SUBMISSION_DB_UNREACHABLE_LEAD = (
    "Submitting records a durable, attributable declaration, and this deployment's "
    "application database did not accept the connection, so none could be recorded. "
    "This is an operator or infrastructure condition, not something about this "
    "record."
)


# =============================================================================
# THE SUBMIT REFUSAL PARTITION, DECLARED ONCE AND PINNED AGAINST THE CODE
# =============================================================================
#
# WHAT WAS WRONG, AND WHY IT WAS NOT COSMETIC. The `409` description used to
# enumerate its seven errors and then split them positionally: *"The first four are
# raised before any official record is materialised. The last three can also be
# raised after materialisation."* Measured against the call sites, that split was
# wrong in three places at once:
#
#   * `already_submitted` was in the "first four" and IS raised after materialisation
#     — `_already_submitted(exc.existing, published)` and `_already_submitted(settled,
#     published)`, both inside the post-materialisation `except` handlers, and its own
#     docstring says so ("reachable from two places");
#   * `sibling_link_conflict` was in the "last three" and is raised ONLY before —
#     its single call site sits immediately above the `MATERIALISE, THEN RECORD`
#     block;
#   * `submission_blocked` is raised from TWO places, one of them textually inside
#     the materialisation block (the `materialisation.failures` branch), which a
#     reader checking the claim by eye would score as post-materialisation.
#
# So no edit to the words "four" and "three" could make the sentence true: the
# positional split did not correspond to the real partition, and a hand-maintained
# tally in a safety-relevant contract is the shape `db_write._FORBIDDEN_KEYWORDS`
# already records drifting ("that count read eight while the pinning test already
# enumerated NINE").
#
# WHY IT IS CRITICAL RATHER THAN A DOC NIT. It is the same defect
# `_publication_disclosure` (C1) exists to close, one layer out. The response BODY
# gets it right — every refusal carries `published_record_count` and `records`. The
# PUBLISHED CONTRACT did not, so a client author reading the OpenAPI document before
# calling learned `already_submitted => nothing published`, and that is the
# unrecoverable case: exported records are immutable and no route republishes one, so
# a scientist told nothing was written will edit the record and retry, and the
# artifacts permanently hold the pre-edit science.
#
# THE FIX IS STRUCTURAL, NOT EDITORIAL. Positional phrasing is gone; each refusal
# carries its own marker, rendered from this ONE table, and
# `test_submit_refusal_partition.py` derives the same partition from the ABSTRACT
# SYNTAX TREE of `post_submit` and fails if the two disagree — so a refusal that
# changes materialisation side, or a new one that is added, cannot leave this prose
# behind.
#
# THE DISCRIMINATOR IS THE PUBLICATION DISCLOSURE, NOT THE LINE NUMBER, and that
# choice is what makes the derivation right where reading by eye is wrong. A refusal
# "can have published" exactly when its emission is handed `published` — helper call
# sites pass it, inline bodies splat `_publication_disclosure`'s fields. Measured,
# that classifies the second `submission_blocked` correctly as `never`: it is
# textually after the materialisation comment, but `_materialise_pending_units`
# validates EVERY unit before writing ANY (its PHASE 1 returns `written=False`), so
# nothing is on disk when it fires. A positional rule would have marked it `always`
# and published a second false claim while fixing the first.
#
#: `never`  — this refusal is never raised with records already published.
#: `either` — reachable from both sides; only `published_record_count` says which.
#: `always` — only reachable after publication.
_SUBMIT_REFUSAL_PUBLICATION: tuple[tuple[int, str, str, str], ...] = (
    # `human_actor_required` is raised by `require_human_actor`, a DEPENDENCY, so it
    # resolves before the handler body runs and cannot be post-materialisation by
    # construction. The pinning test asserts it is emitted nowhere inside the
    # handler rather than taking that on trust.
    (409, "human_actor_required", "this deployment cannot establish who is calling", "never"),
    (409, "tutorial_scope_forbidden", "a worked-example session is never submitted", "never"),
    (
        409,
        "submission_blocked",
        "unanswered questions, or a unit whose export does not pass",
        "never",
    ),
    (
        409,
        "sibling_link_conflict",
        "publishing would falsify a link a surviving sibling record already carries",
        "never",
    ),
    (
        409,
        "already_submitted",
        (
            "this record's published content and conflict decisions are already on "
            "record; the existing submission is echoed"
        ),
        "either",
    ),
    (409, "idempotency_key_conflict", "that key was used for different content", "either"),
    (
        409,
        "submission_conflict",
        "a concurrent writer won and its row could not be read back",
        "always",
    ),
    # The 503 reasons, for the same reason and with the same defect: the 503
    # description named `tables_absent` as the one raisable "from the write itself,
    # after the official records have been published" and said nothing about
    # `database_unavailable`, which is raised from the write's own
    # `except db_write.WriteRefused` handler and is just as post-materialisation.
    (503, "no_durable_storage", "this deployment has no application database", "never"),
    (503, "database_unavailable", "the database did not accept a connection", "either"),
    (
        503,
        "tables_absent",
        "the tables a submission is recorded in do not exist yet",
        "either",
    ),
)

#: How each marker reads to a client. Deliberately about what is ON DISK rather than
#: about where in the handler the refusal came from: the caller cannot see the
#: handler, and the fact they must act on is whether artifacts exist.
_PUBLICATION_MARKER_PROSE = {
    "never": "nothing was published",
    "either": "**may already have published** — read `published_record_count`",
    "always": "**published before it was refused**",
}


def _refusal_partition_lines(status: int) -> str:
    """The enumeration for one status code, rendered from the table above.

    Rendered rather than written out so the prose cannot disagree with the table,
    and NO COUNT IS EMITTED anywhere in it — nor in either description around it.
    The count that used to open the split ("the first four…") is precisely what
    could not be corrected by editing, so no replacement tally is introduced here.
    """
    return "\n".join(
        f"- `{name}` — {gloss} — {_PUBLICATION_MARKER_PROSE[marker]}"
        for code, name, gloss, marker in _SUBMIT_REFUSAL_PUBLICATION
        if code == status
    )


_SUBMIT_409_DESCRIPTION = (
    "The submission was refused and **no submission was recorded**. That half is "
    "unconditional: no submission row exists on any of these paths.\n\n"
    "**Whether anything was PUBLISHED is a separate question, and it depends on "
    "which refusal this is.** Official ISAAC records are published BEFORE the "
    "submission transaction is opened — deliberately, because it is the only "
    "recoverable order — so some of these can arrive with records already on "
    "disk. `error` says which refusal this is:\n\n"
    + _refusal_partition_lines(409)
    + "\n\n`published_record_count` and `records` are present on every one of these "
    "bodies EXCEPT `human_actor_required`, and are the authoritative answer for a "
    "given response; the markers above say only which refusals can carry a non-zero "
    "count. `human_actor_required` is raised before this operation's own handler "
    "runs — by the dependency that establishes who is calling, which is shared with "
    "any operation that needs an attributable person and states nothing about "
    "publication — so it carries neither field, and nothing can have been published "
    "when it fires. Reading `published_record_count` with a default of `0` is "
    "therefore correct on every body above. A non-zero count means those "
    "records exist on disk and, being immutable, will not be republished by a retry — "
    "so editing this record before retrying leaves the published files holding the "
    "content submitted here."
)

_SUBMIT_503_DESCRIPTION = (
    "This deployment cannot record a submission: it is not configured with an "
    "application database, that database did not accept a connection, or it does not "
    "yet have the tables. `error` is `submission_unavailable` and `reason` "
    "distinguishes them.\n\n"
    "As with the `409`s, whether anything was PUBLISHED depends on which reason it "
    "is — normally nothing, because the storage question is asked first with reads "
    "only, but some of these are also raised from the write itself, after the "
    "official records have been published:\n\n"
    + _refusal_partition_lines(503)
    + "\n\n`published_record_count` and `records` say what this request published "
    "before it was refused, on every one of these bodies."
)


@router.post(
    "/experiments/{experiment_id}/submit",
    tags=[TAG_EXPORT],
    summary="Submit a Record",
    description=(
        "Finalises this record: it publishes an official ISAAC record for every "
        "unit that does not have one yet, and then records a durable, attributable "
        "submission over exactly that content, together with an immutable snapshot "
        "of the record as it was.\n\n"
        "**Submitting is not the same as exporting, and neither implies the other.** "
        "Exporting is a mechanical transform that answers whether a record "
        "validates; anyone can run it, at any time. Submitting is a declaration by a "
        "named person that the work is finished. Exporting a record therefore never "
        "marks it submitted, and this operation records who submitted it, when, and "
        "over which content.\n\n"
        "It requires an attributable person. A deployment that cannot establish who "
        "is calling refuses with `409` and writes nothing — no partial submission, "
        "no anonymous one, and no official record.\n\n"
        "The gate is the record's own export-readiness and nothing more: every "
        "question must be answered and every unit's export must pass its dry run. A "
        "refusal names the units that failed and why. There is no override and no "
        "force parameter, because a record that is not ready to export cannot be "
        "finalised.\n\n"
        "*Stated precisely, because the shorter phrase \"exactly the export gate\" "
        "is not quite true: these are the two conditions `Experiment.export_ready()` "
        "composes, and `POST .../export` itself checks only the second — it will "
        "publish a record with unanswered questions. Submitting adds no rule beyond "
        "export-readiness, but it does apply the answered-questions half that the "
        "export route does not.*\n\n"
        "**Evidence conflicts are reported, not blocked on.** A field whose evidence "
        "asserts two different values is recorded in the submission and returned in "
        "`conflict_summary`, and the submission proceeds. Correcting an answer adds a "
        "second confirmation rather than replacing the first, so blocking on this "
        "would refuse a record forever for the act of fixing a typo.\n\n"
        "**What was published may not be what you submitted, and the response says "
        "so.** Exported records are immutable, so a record you exported and then "
        "edited is not republished by submitting — `published_artifact_state` "
        "reports `stale` in that case, and `current` when the records on disk match "
        "the content you submitted. It is reported rather than refused, because "
        "there is no operation that republishes an immutable record, so refusing "
        "would leave you with no way forward.\n\n"
        "Submitting the same unchanged content twice is safe. The second call is "
        "refused with `409` and echoes the submission already on record, so nothing "
        "is duplicated. Send an `Idempotency-Key` header to have an exact retry "
        "return the original `200` instead — the same key with different content is "
        "refused rather than silently replayed.\n\n"
        "Requires the record's current `ETag` in `If-Match`."
    ),
    response_description=(
        "The recorded submission: its id, the revision snapshot it captured, the "
        "records it published, the server-assigned time, who it is attributed to and "
        "on what basis, and any evidence conflicts it disclosed."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        **_R_PRECONDITION,
        412: {
            "description": (
                "The write was refused because another writer got there first, so "
                "your change was not applied and the response echoes the current "
                "`ETag` so a client can refresh in one further request.\n\n"
                "Two arms, and they differ in what is left behind. If `If-Match` did "
                "not match the revision this server read, nothing at all was "
                "written. If the record's stored copy moved on while the official "
                "records were being published, those records had ALREADY been "
                "written and they remain — the record's own state was not updated, "
                "so it still reports as not exported, and no submission was "
                "recorded. Retrying republishes only what is missing and then "
                "records the submission."
            )
        },
        409: {"description": _SUBMIT_409_DESCRIPTION},
        503: {"description": _SUBMIT_503_DESCRIPTION},
    },
)
def post_submit(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    # THE DEPENDENCY, NOT A CALL IN THE BODY — and one observable consequence is
    # stated here rather than left to be discovered. FastAPI resolves dependencies
    # BEFORE the handler runs, so the attributability refusal precedes the 404: a
    # deployment that cannot attribute anyone answers 409 for an id that does not
    # exist, instead of 404. That ordering is kept, for two reasons. It is the
    # designed seam — `identity.require_human_actor` is the only way to an actor and
    # the handler never touches identity resolution itself, which is what keeps
    # `if header exists: trust it` unwritable from here. And it is the safer order:
    # a caller this deployment cannot attribute learns nothing about which record ids
    # exist. Every other refusal below is in the documented order, and none of them
    # writes anything.
    identity: Annotated[Any, Depends(require_human_actor("submit"))],
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The record's current `ETag`, exactly as a read operation "
            "returned it."
        ),
    ),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description=(
            "Optional. An opaque client-chosen value. Repeating a submission with "
            "the same key and the same content replays the original result; the same "
            "key with different content is refused."
        ),
    ),
):
    # Cheap existence pre-check OUTSIDE the lock so a bogus/non-existent id never
    # creates a permanent entry in the never-evicting per-record lock map. Same
    # reasoning, same placement, as `post_export`.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)

    # A WORKED-EXAMPLE SESSION IS NEVER SUBMITTED. The session is temporary and
    # synthetic and is discarded with its records, so a durable declaration over one
    # would outlive the thing it declares, attached to fabricated science. This is
    # the FIRST of three independent enforcements — `stamp_actor` refuses to name an
    # actor in any scoped request, and `PostgresOrdinaryStore.refuse_if_not_persistable`
    # raises on a session record and on a canonical example id in any scope.
    if scope is not None:
        return JSONResponse(
            status_code=409,
            content={
                "error": "tutorial_scope_forbidden",
                "operation": "POST /api/experiments/{experiment_id}/submit",
                "header": TUTORIAL_SESSION_HEADER,
                "message": (
                    "Records in a worked-example session are temporary and are "
                    "discarded with the session, so they are never submitted. "
                    "Nothing was written."
                ),
                # Measured lacking both keys the 409 description promises on every
                # body: `['error', 'header', 'message', 'operation']`. See
                # `_publication_disclosure`.
                **_NOTHING_PUBLISHED_FIELDS,
            },
        )

    key = idempotency_key.strip() if idempotency_key is not None else None
    if idempotency_key is not None and (
        not key or len(key) > submission_store.IDEMPOTENCY_KEY_MAX
    ):
        # A REQUEST-SHAPE REFUSAL, and it is 400 rather than 422 to match
        # `malformed_if_match`: both are malformed HEADERS, and a client that has to
        # learn two codes for one class of mistake learns the wrong lesson. The bound
        # exists because the column has no length limit of its own, so an unbounded
        # header would otherwise become an unbounded row; the emptiness check exists
        # because `''` is a key every keyless retry could collide with, which the
        # database CHECK also refuses.
        return JSONResponse(
            status_code=400,
            content={
                "error": "malformed_idempotency_key",
                "experiment_id": experiment_id,
                "message": (
                    "Idempotency-Key must be a non-empty value of at most "
                    f"{submission_store.IDEMPOTENCY_KEY_MAX} characters."
                ),
            },
        )

    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window

        err = _check_if_match(if_match, exp)
        if err is not None:
            return err

        pre_steps = _workflow_for(exp)["ordered_steps"]
        units = exp.export_units()
        signature = submissions.content_signature(exp.id, units)

        # ---- STORAGE, BEFORE ANY ARTIFACT IS WRITTEN --------------------------
        # The order is the point. Materialisation writes files and saves state; if
        # the submission could not be recorded anyway, none of that should happen.
        # So the storage question is asked FIRST, and it is asked with reads only.
        store = submission_store.store()
        if store is None:
            return _submission_unavailable(
                submission_store.BLOCKER_NO_DURABLE_STORAGE,
                _SUBMISSION_NO_STORAGE_LEAD,
            )
        try:
            preflight = store.preflight(exp.id, signature, key)
        except db_write.WriteRefused:
            # I1 — A CONFIGURED DATABASE THAT DOES NOT ANSWER IS A 503, NOT A 500.
            # `store()` gates on the same two conditions `experiment_repository`
            # does, so a wrong `PGDATABASE` never reaches here — but a database that
            # is configured, correctly named and simply unreachable does, and
            # `WriteRefused` is raised from inside `write_transaction` with no
            # handler registered for it anywhere. Before this branch that surfaced as
            # a bare 500, which is exactly what `_submission_unavailable`'s docstring
            # promises will not happen and disagrees with `/api/health`, which
            # already reports the deployment as unable to record a submission.
            #
            # The message is path-free and credential-free by construction:
            # `WriteRefused` carries a fixed string and it is not interpolated here.
            return _submission_unavailable("database_unavailable", _SUBMISSION_DB_UNREACHABLE_LEAD)
        if not preflight["tables_present"]:
            return _submission_unavailable("tables_absent", _SUBMISSION_NO_TABLES_LEAD)

        # ---- ALREADY SUBMITTED ------------------------------------------------
        # An exact repeat with the SAME key is a replay and returns the original
        # 200; without a key — or with a different one — it is a 409 that echoes
        # what is already on record. The distinction is what an `Idempotency-Key`
        # is FOR: a client that cannot tell a lost response from a duplicate
        # request needs the retry to succeed, and a client that did not ask for
        # that needs to be told it already submitted.
        existing = preflight["by_signature"]
        if existing is not None:
            if key is not None and existing.get("idempotency_key") == key:
                return _submission_replay(exp, existing, response)
            return _already_submitted(existing)
        by_key = preflight["by_key"]
        if by_key is not None:
            return _idempotency_key_conflict(by_key)

        # ---- HARD BLOCKERS: EXACTLY EXPORT-READINESS --------------------------
        # `pending_count() == 0` over every unit, AND every unit's export dry run
        # passes. No new rule, no fifth reason, no "Submit Anyway" — contract §3 D4.
        #
        # M5 — "exactly the export GATE" is the phrasing this comment and two others
        # used, and it overstates by one condition. These two are exactly
        # `Experiment.export_ready()`; `POST .../export` checks only the dry run and
        # has no `pending_count()` test at all, so it will publish a record with
        # unanswered questions. Submit adds nothing to export-readiness — but it is
        # not identical to what the export ROUTE enforces, and the difference is in
        # the direction of being stricter.
        blockers = submissions.blocker_report(exp, units)
        if blockers["blocked"]:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "submission_blocked",
                    "experiment_id": exp.id,
                    "message": (
                        "This record cannot be submitted yet. Every question must be "
                        "answered and every record it would publish must pass the "
                        "export check. Nothing was written."
                    ),
                    "pending_count": blockers["pending_count"],
                    "pending": blockers["pending"],
                    "failing_units": blockers["failing_units"],
                    # Refused before anything is materialised. See
                    # `_publication_disclosure`.
                    **_NOTHING_PUBLISHED_FIELDS,
                },
            )

        conflict = _sibling_link_conflict(exp, units)
        if conflict is not None:
            return conflict

        # ---- MATERIALISE, THEN RECORD. ORDER IS RECOVERABILITY ----------------
        # Artifacts and state first, submission rows second. A fault between them
        # leaves records on disk and no submission — and a retry finds every unit
        # already materialised, skips the export entirely, recomputes the SAME
        # signature (it excludes `record_id`, `rev` and every timestamp precisely so
        # that it can) and writes the rows. The reverse order is NOT recoverable: a
        # submission naming records that were never written is indistinguishable
        # from one whose files were later deleted.
        #
        # A unit that is already materialised is skipped here exactly as it is in
        # `post_export`: never revalidated, never rewritten. So submitting a
        # fully-exported record publishes nothing and records the declaration, which
        # is the whole reason submit does not call the export route (that route
        # answers 409 in precisely that case).
        pending_units = [unit for unit in units if not unit.materialised()]
        published: list[dict] = []
        changed = False
        # Resolved BEFORE materialisation because materialisation is what writes the
        # artifacts, and the server-owned `attribution.uploaded_by` stamp has to be in
        # the bytes that reach the disk.
        #
        # THIS IS NOT THE SAME VALUE AS THE SUBMISSION ROW'S `subject` BELOW, and an
        # earlier revision of this slice bound them to one name on the reasoning that
        # "a record published by a submission and the row that records it must not be
        # able to disagree about who did it." That reasoning is wrong, and binding them
        # silently stripped the row's fixture attribution — caught by
        # `test_submission.py::test_the_recorded_subject_is_labelled_test_fixture_...`.
        #
        # They differ because the two destinations can carry different amounts of truth.
        # A submission row stores `trust_basis` beside the subject, so a fixture-
        # attributed row SAYS SO ABOUT ITSELF — which is the mitigation
        # `FixtureEdgeVerifier` stakes its existence on. An official ISAAC record has no
        # such field: `attribution.uploaded_by` means "Authenticated identity that
        # submitted this record" and cannot be qualified. So the row may name a subject
        # the record may not, and `record_attribution.resolve_uploaded_by` is where that
        # one extra gate lives. `None` on every deployment shipped today, both ways.
        submit_uploaded_by = record_attribution.resolve_uploaded_by(identity, scope)
        if pending_units:
            materialisation = _materialise_pending_units(
                exp, pending_units, if_match, units=units,
                uploaded_by=submit_uploaded_by,
            )
            if materialisation.failures:
                # Reachable even though `blocker_report` just passed, and the gap is
                # real rather than defensive: the blocker dry run calls
                # `export_draft` WITHOUT a `record_id` (matching
                # `Experiment._all_units_pass_dry_run`), while materialisation passes
                # `unit.target_id`. A unit whose id is not a ULID therefore passes the
                # first and fails the second. Nothing was written in that case.
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": "submission_blocked",
                        "experiment_id": exp.id,
                        "message": (
                            "This record could not be published. The export check "
                            "passed for its drafts but refused when the official "
                            "records were built. Nothing was written."
                        ),
                        "pending_count": blockers["pending_count"],
                        "pending": blockers["pending"],
                        "failing_units": [
                            {
                                "unit_id": unit.target_id,
                                "run_id": unit.run_id,
                                "run_label": unit.run_label,
                                "errors": _flat_export_errors(
                                    serialize.export_result_to_dict(result), result
                                ),
                            }
                            for unit, result in materialisation.failures
                        ],
                        # STILL `never`, and the reason is `_materialise_pending_units`
                        # PHASE 1 rather than this body's position in the file: it
                        # validates every unit before writing any, and returns
                        # `written=False`. The partition test derives that from the
                        # code for exactly this reason — a positional reading would
                        # classify this emission `always` and publish a false claim
                        # while fixing another.
                        **_NOTHING_PUBLISHED_FIELDS,
                    },
                )
            if materialisation.stale is not None:
                return materialisation.stale
            changed = materialisation.changed
            published = [_unit_artifact_entry(unit) for unit, _ in materialisation.results]

        # ---- THE DURABLE WRITE ------------------------------------------------
        # `stamp_actor` rather than `identity.human.subject`: it is the one place the
        # tutorial rule and the tier rule are written down, and reaching past it
        # would be the "a later slice writes uploaded_by=principal.subject" shape the
        # identity contract warns about. `scope` is None on every path that reaches
        # here (the session refusal is far above), so this returns the subject
        # whenever the deployment can attribute one.
        # `stamp_actor`, NOT `submit_uploaded_by` — see the note above the latter for
        # why the row may name somebody the immutable record may not. This is the one
        # place the worked-example rule and the tier rule are written down, and reaching
        # past it would be the "a later slice writes uploaded_by=principal.subject"
        # shape the identity contract warns about.
        subject = identity_module.stamp_actor(identity, scope)
        trust_basis = (
            identity.human.trust_basis
            if subject is not None and identity.human is not None
            else submissions.TRUST_BASIS_UNATTRIBUTED
        )
        # THE RECORD's decisions, all of them, scoped per unit inside
        # `conflict_summary`. Read here rather than off each unit because
        # `resolved_run_draft` does not copy the key into a run's composed draft —
        # see that function's docstring for why one record-level list is the storage.
        # Unreadable stored entries are ignored for the disclosure and preserved on
        # disk; the count of them is not part of a submission row's contract.
        record_resolutions, _unreadable_resolutions = cr.resolutions_from_draft(exp.draft)
        conflict_summary = submissions.conflict_summary(units, record_resolutions)
        try:
            recorded = store.record_submission(
                exp=exp,
                units=units,
                content_signature=signature,
                conflict_summary=conflict_summary,
                subject=subject,
                trust_basis=trust_basis,
                idempotency_key=key,
            )
        # EVERY REFUSAL BELOW IS RAISED *AFTER* MATERIALISATION, so every one of them
        # is handed `published` and none of them may claim nothing was published. See
        # `_publication_disclosure` for the failure this closes; the four helpers
        # default `published` to empty so the pre-materialisation call sites above
        # keep the sentence they had.
        except submission_store.SubmissionTablesMissing:
            # The tables went away between the preflight and the write. The
            # transaction issued only SELECTs and rolled back, so no submission
            # exists — but any record this request published is on disk and stays
            # there, and the message now says both halves rather than only the first.
            return _submission_unavailable(
                "tables_absent", _SUBMISSION_NO_TABLES_LEAD, published
            )
        except db_write.WriteRefused:
            # I1's other arm: the database stopped answering between the preflight
            # and the write. Untyped by `submission_store` on purpose — it is
            # `db_write`'s refusal, not a submission-lifecycle outcome — and it must
            # not surface as a 500 here any more than it may on the preflight.
            return _submission_unavailable(
                "database_unavailable", _SUBMISSION_DB_UNREACHABLE_LEAD, published
            )
        except submission_store.SubmissionAlreadyExists as exc:
            if key is not None and exc.existing.get("idempotency_key") == key:
                return _submission_replay(exp, exc.existing, response, published)
            return _already_submitted(exc.existing, published)
        except submission_store.IdempotencyKeyConflict as exc:
            return _idempotency_key_conflict(exc.existing, published)
        except submission_store.SubmissionRaceLost:
            # A CONCURRENT WRITER WON. This transaction COMMITTED nothing — and the
            # distinction matters, because unlike the two branches above it did
            # ISSUE inserts (the revision row, its run revisions, its change rows)
            # before losing; what saves the caller is the rollback, not restraint.
            # The winner's row therefore has to be read in a FRESH transaction:
            # reading it inside the loser's would return the loser's own uncommitted
            # view. Whether that is a replay or a refusal is decided exactly as it is
            # on the preflight path, so the loser is answered the same way it would
            # have been had it arrived one moment later.
            #
            # The lookup itself can fail against a database that has just stopped
            # answering, and a 500 raised while reporting a conflict would be the
            # worst of both: `winner` is therefore defaulted to "found nothing",
            # which falls through to the honest generic conflict below.
            try:
                winner = store.lookup(exp.id, signature, key)
            except db_write.WriteRefused:
                winner = {"tables_present": False, "by_signature": None, "by_key": None}
            settled = winner["by_signature"]
            if settled is not None:
                if key is not None and settled.get("idempotency_key") == key:
                    return _submission_replay(exp, settled, response, published)
                return _already_submitted(settled, published)
            if winner["by_key"] is not None:
                return _idempotency_key_conflict(winner["by_key"], published)
            # The winner is gone or unreadable. Reporting a specific outcome here
            # would be inventing one; 409 with the honest reason is the answer.
            note, fields = _publication_disclosure(published)
            return JSONResponse(
                status_code=409,
                content={
                    "error": "submission_conflict",
                    "experiment_id": exp.id,
                    "message": (
                        "Another submission of this record was recorded at the same "
                        f"moment, so this one was not. {note} Re-read the record and "
                        "try again."
                    ),
                    **fields,
                },
            )

        payload = dict(recorded)
        payload["records"] = published
        payload["published_record_count"] = len(published)
        # DISCLOSED, NOT GATED ON — and this one is a defect I found while writing
        # the real-engine proof rather than a hypothetical.
        #
        # Exported records are IMMUTABLE, so a unit that was already materialised is
        # skipped here and never rewritten. Edit a draft after exporting it and the
        # record on disk stops being a faithful projection of the draft — and a
        # submission over that draft then names record ids whose artifacts hold
        # something else. Saying nothing would let the response imply that what was
        # submitted is what was published.
        #
        # IT IS NOT A REFUSAL, because the hard-blocker gate is EXACTLY
        # export-readiness and nothing more (contract §3 D4, and the instruction this
        # slice was built to; see the M5 note at the blocker check for why that is
        # not word-for-word the same as "what `POST .../export` enforces"). Adding a
        # fifth reason here would create a state a scientist cannot resolve through
        # any surface this application offers: there is no route that republishes an
        # immutable record.
        #
        # IT IS DERIVED AND DELIBERATELY NOT STORED. `dependencies.artifact_state` is
        # the ONE definition of this freshness in the application — the record detail
        # screen already renders it — and it is recomputable at any time from the
        # revision snapshot and the artifacts. A column would be a second copy that
        # can disagree with the first, and it would need its own migration.
        payload["published_artifact_state"] = dependencies.artifact_state(exp)
        payload.update(vc.version_fields(exp))
        payload["workflow"] = _workflow_for(exp)
        payload["invalidation"] = dependencies.build_invalidation(
            changed=changed,
            changed_fields=["record_id"] if changed else [],
            pre_steps=pre_steps,
            post_exp=exp,
        )
        response.headers["ETag"] = exp.etag()
        return payload


def _already_submitted(
    existing: dict, published: Sequence[dict] | None = None
) -> JSONResponse:
    """``409``, echoing the submission already on record. No submission was recorded.

    ``published`` DEFAULTS TO EMPTY AND IS NOT OPTIONAL AT THE POST-RACE CALL SITES.
    This refusal is reachable from two places: the preflight, before any official
    record is materialised, and the write, after every one of them is. The old
    single sentence — "nothing was written and nothing was published again" — was
    true of the first and false of the second. See :func:`_publication_disclosure`.

    **THE MESSAGE NO LONGER SAYS "WITH EXACTLY THIS CONTENT", AND THAT WORDING WAS A
    MEASURED HONESTY DEFECT RATHER THAN A CLUMSY PHRASE.** The comparison is
    ``submissions.content_signature``, whose scope is narrower than the document: it
    deliberately excludes the title, the notes, the captured transcript and every
    other piece of workspace state (that function lists each exclusion and why). So a
    scientist who captured a note, renamed the record, or — before the signature was
    widened — recorded a conflict decision, was told the record was unchanged by the
    very request that had just moved it, and had no way to tell which of their work
    the submission on file actually covers. The message now names the comparison's
    scope instead of asserting whole-document identity, and it says what a
    resubmission would therefore never record.
    """
    note, fields = _publication_disclosure(published)
    return JSONResponse(
        status_code=409,
        content={
            "error": "already_submitted",
            "message": (
                "A submission is already on record for this record's published "
                "content and its conflict decisions, so no second submission was "
                f"recorded. {note} Workspace-only changes are outside that "
                "comparison — the title, captured notes and the transcript are not "
                "compared, so changing one does not make this a new submission. Send "
                "an Idempotency-Key with your original key if you are retrying a "
                "request whose response you did not receive."
            ),
            "submission": existing,
            **fields,
        },
    )


def _idempotency_key_conflict(
    existing: dict, published: Sequence[dict] | None = None
) -> JSONResponse:
    """``409`` for a reused key over different content.

    SEPARATE FROM ``already_submitted`` BECAUSE THE REMEDY IS DIFFERENT. One says
    "you already did this, here is the receipt"; this one says "your key is reused,
    choose a new one". A client cannot act on a merged message, and merging them
    would make a genuine replay indistinguishable from a client bug.

    ``published`` for the same reason as above: this is raised both before and after
    materialisation, and only the caller knows which.
    """
    note, fields = _publication_disclosure(published)
    return JSONResponse(
        status_code=409,
        content={
            "error": "idempotency_key_conflict",
            "message": (
                "That Idempotency-Key was already used for a submission of "
                f"different content, so this request was refused. {note} Use a new "
                "key."
            ),
            "submission": existing,
            **fields,
        },
    )


def _submission_replay(
    exp, existing: dict, response: Response, published: Sequence[dict] | None = None
) -> dict:
    """The original ``200`` for an exact retry under the same ``Idempotency-Key``.

    ``replayed: true`` IS PART OF THE BODY AND IS NOT COSMETIC. A client that cannot
    tell a first success from a replay cannot tell whether its own retry logic is
    working, and a UI that says "submitted just now" over a submission recorded an
    hour ago is asserting a time that did not happen. Everything else in the body is
    the ORIGINAL row read back from the database — the original id, the original
    revision, the original server-assigned timestamp — because a replay reports what
    is on record, never a fresh rendering of what would have been written.

    ``records`` AND ``published_record_count`` REPORT WHAT **THIS** REQUEST
    PUBLISHED, WHICH IS USUALLY NOTHING AND IS NOT ALWAYS NOTHING. On the preflight
    path — an exact retry that finds the original row before doing anything — they
    are empty, and the records the original submission published are named by that
    submission's own rows rather than claimed here. But this helper is ALSO reached
    after a lost race, by which point this request may itself have materialised
    official records; the earlier unconditional zero asserted otherwise. The caller
    passes what it published and this reports it, for the reason set out at
    :func:`_publication_disclosure`.
    """
    entries = list(published or [])
    payload = dict(existing)
    payload["replayed"] = True
    payload["records"] = entries
    payload["published_record_count"] = len(entries)
    # PRESENT ON THIS PATH TOO, so a client never has to branch on whether a key
    # exists. It describes the artifacts as they are NOW, which on a replay may
    # differ from how they were when the original submission was recorded — that is
    # the honest reading of a derived signal, and it is why the key is derived
    # rather than replayed out of the stored row.
    payload["published_artifact_state"] = dependencies.artifact_state(exp)
    payload.update(vc.version_fields(exp))
    payload["workflow"] = _workflow_for(exp)
    payload["invalidation"] = dependencies.build_invalidation(
        changed=False, changed_fields=[], pre_steps=_workflow_for(exp)["ordered_steps"], post_exp=exp
    )
    response.headers["ETag"] = exp.etag()
    return payload


# --- 8a2. THE REVISION HISTORY READ SURFACE (read-only, writes nothing) -------
#
# WHAT THESE THREE OPERATIONS ARE, AND THE ONE THING THEY MUST NEVER DO.
#
# `POST .../submit` captures an immutable snapshot of a record and records a
# declaration over it. Until this section existed there was NO WAY TO READ ANY OF
# THAT BACK: the rows were written and were reachable only by a psql session. These
# three GETs are that read surface, and they add no write of any kind — no route
# here mints a revision, and the only writer of `isaac_experiment_revisions` is
# still `submission_store.record_submission`, inside its one transaction.
#
# THE ONE THING THEY MUST NEVER DO IS ANSWER "NO HISTORY" WHEN THE TRUTH IS
# "CANNOT KNOW". Migrations `0003_revisions` and `0004_submissions` are applied by
# an OPERATOR, separately from the image rollout, so a running build routinely meets
# a database its own migrations have not reached — and on this deployment they have
# not been applied at all. An empty `revisions: []` in that state is a lie with a
# plausible shape: it says "this record was never submitted" about a database this
# server never successfully asked. So every operation here reports `availability` as
# a FIRST-CLASS field, `revisions` exists ONLY when the history was actually read,
# and the three ways it can be unreadable are named separately because they have
# three different remedies (configure a database / apply a migration / restore one
# that stopped answering).
#
# THE STORED DOCUMENT NEVER LEAVES THE PROCESS. `isaac_experiment_revisions.state`
# is a whole experiment snapshot and `revision_history.Q_REVISION_BY_NO` fetches it,
# because the diff is computed from it. No response body below carries it: the
# payload builders name their fields one by one, and a test asserts the detail body
# has no `state` key.


#: The three ways the history can be unreadable, as prose. Each names its own
#: remedy, because merging them would send an operator to the wrong place — the
#: same reasoning `_SUBMISSION_NO_TABLES_LEAD` and its two siblings are split on.
_HISTORY_NO_STORAGE_LEAD = (
    "Submission history is a durable record, and this deployment is not configured "
    "with an application database to keep one in. Nothing about this record's "
    "submission history can be read here — which is not the same as this record "
    "never having been submitted."
)
_HISTORY_NO_TABLES_LEAD = (
    "This deployment's database does not yet have the submission-history tables, so "
    "the history could not be read. The migration that creates them has to be "
    "applied by an operator. This is not a statement that this record has never "
    "been submitted — it is a statement that this server could not find out."
)
#: Deliberately says "the read did not complete" rather than naming a CAUSE.
#:
#: It used to say the database "did not accept the connection". That was true of
#: the two connection-layer exceptions this once caught, and false of everything
#: the catch now covers: a statement-policy refusal, a cancelled query, a
#: `lock_timeout`, a dropped connection mid-transaction, a column missing from a
#: drifted migration. Naming the wrong cause is worse than naming none — it sends
#: an operator to the network when the answer is in the code.
#:
#: What it must keep saying, and does: this is an operator condition, not a fact
#: about the record, and emphatically not "never submitted".
_HISTORY_DB_UNREACHABLE_LEAD = (
    "This deployment could not complete the read of its application database, so the "
    "submission history could not be read. This is an operator or infrastructure "
    "condition, not something about this record, and it is not a statement that "
    "this record has never been submitted."
)
#: The FOURTH case, and the one that is NOT an unknown. A worked-example session is
#: refused by `post_submit` outright, `identity.stamp_actor` returns `None` for any
#: scoped request, and `PostgresOrdinaryStore.refuse_if_not_persistable` raises on a
#: session record — three independent enforcements. So "this record has no submission
#: history" is a fact here rather than an inability, and it is reported as its own
#: state so that it can never be confused with the three above.
_HISTORY_WORKED_EXAMPLE_LEAD = (
    "Records in a worked-example session are temporary and are discarded with the "
    "session, so they are never submitted and have no submission history. Nothing "
    "was read, and nothing could have been there to read."
)

#: THE ``503`` THE THREE HISTORY OPERATIONS CAN ANSWER, DECLARED BECAUSE THEY CAN.
#:
#: It covers BOTH 503s these handlers can produce, and it has to, because OpenAPI
#: admits one description per status code and both are reachable on one operation:
#: the record read can raise the durable-storage outage ``_R_STORAGE_UNAVAILABLE``
#: describes, and the history read can find no database, no tables, or a database
#: that did not answer. Declaring only one of them would leave a client meeting the
#: other with a status the contract does not admit exists — the same defect
#: ``_R_STORAGE_UNAVAILABLE``'s own note records being corrected for.
_R_REVISION_HISTORY_UNAVAILABLE: dict = {
    503: {
        "description": (
            "The submission history could not be read, and the body says which of "
            "the reasons applies in `availability.reason`: `no_durable_storage` "
            "(this deployment has no application database), `tables_absent` (it has "
            "one and the migration creating the history tables has not been "
            "applied), or `database_unavailable` (it did not answer). **The rows "
            "key is absent rather than empty**, because \"this record was never "
            "submitted\" and \"this server could not find out\" are different "
            "statements and only one of them was observed. The same status is also "
            "returned when this deployment stores experiments in its own database "
            "and the server could not find out whether that database holds this "
            "record. Nothing is changed either way, and no host, path or credential "
            "is named."
        )
    },
}

#: The ``404`` the two per-revision operations can answer, which is TWO facts.
_R_REVISION_NOT_FOUND: dict = {
    404: {
        "description": (
            "Either no experiment in the selected workspace has that id — or the "
            "record exists, its history was read successfully, and it holds no "
            "revision under that number. The body's `error` distinguishes them "
            "(`experiment_not_found` / `revision_not_found`), because they send a "
            "reader to different places."
        )
    },
}

#: `availability.state`, as three stable machine-readable values.
_HISTORY_AVAILABLE = "available"
_HISTORY_UNAVAILABLE = "unavailable"
_HISTORY_NOT_APPLICABLE = "not_applicable"


def _history_availability(state: str, reason: str | None, message: str) -> dict:
    """The one shape every history operation reports its availability in.

    ``reason`` is ``None`` only for ``available``. Every other state names its cause
    with a stable code so a client branches on the code and renders the message.
    """
    return {"state": state, "reason": reason, "message": message}


def _submission_deployment_block() -> dict:
    """Why this deployment could not accept a submission — SEPARATELY from the science.

    **THIS IS THE FIELD THAT KEEPS `ready_to_submit` HONEST.** A record whose every
    question is answered and whose every unit passes the export gate IS ready to
    submit, and stays ``ready_to_submit`` on a deployment that can record nothing at
    all. Whether a submission would be ACCEPTED is a different question about a
    different subject — this server's configuration — and it is answered here, under
    its own name, so that an operator problem can never read as an unfinished record.

    It reuses ``submission_store.capability()`` verbatim rather than re-deriving the
    conditions: that function is what ``GET /api/health`` already publishes, and two
    surfaces of one deployment disagreeing about whether it can submit is precisely
    the defect its own docstring records being corrected for. It opens nothing.

    Worth stating because it is this build's normal state: ``no_attributable_actor``
    is present on every deployment shipped today. ``identity.require_human_actor``
    reaches an actor only through a configured verifier, no shipped deploy artifact
    configures one, and therefore ``POST .../submit`` refuses every request with
    ``409 human_actor_required``. That is a deployment fact. It is NOT a fact about
    any record, and nothing here lets it become one.
    """
    capability = submission_store.capability()
    blockers = list(capability["blockers"])
    if not blockers:
        message = (
            "This deployment is configured to accept a submission. Whether one "
            "would succeed also depends on the database holding the "
            "submission-history tables, which cannot be known without writing."
        )
    else:
        message = (
            "This deployment cannot currently accept a submission of any record. "
            "This says nothing about whether this record is ready — it is a fact "
            "about how this server is configured, and it is resolved by an "
            "operator, not by editing the record."
        )
    return {
        "blocked": bool(blockers),
        "blockers": blockers,
        "basis": capability["basis"],
        "requires_attributable_actor": capability["requires_attributable_actor"],
        "actor_trust_basis": capability["actor_trust_basis"],
        "message": message,
    }


def _lifecycle_payload(
    exp,
    units: Sequence[Any],
    *,
    submitted_known: bool,
    submitted_for_current_content: bool | None,
    unknown_reason: str | None,
) -> dict:
    """The derived lifecycle, plus the deployment disclosure beside it.

    ``blocker_report`` IS CALLED, NOT REIMPLEMENTED. It is the one definition of what
    blocks a submission — ``pending_count() == 0`` over all units, and every unit's
    ``export_draft`` dry run passing — and it never raises. Deriving the lifecycle
    from anything else would create a second answer to "is this ready", which is the
    exact class of defect ``_workflow_for``'s own comment records being fixed.

    The derivation itself is ``workflow.derive_lifecycle``, which is pure and takes
    NO deployment input and NO ``exported`` input. Everything environmental is
    attached here, under its own key.
    """
    blockers = submissions.blocker_report(exp, units)
    lifecycle = derive_lifecycle(
        pending_count=int(blockers["pending_count"]),
        failing_unit_count=len(blockers["failing_units"]),
        submitted_known=submitted_known,
        submitted_for_current_content=submitted_for_current_content,
        submission_unknown_reason=unknown_reason,
    )
    lifecycle["submission_blocked_by_deployment"] = _submission_deployment_block()
    # The per-unit detail behind `failing_unit_count`, so a refusal names WHICH unit
    # refused rather than only that one did. Same list `POST .../submit` refuses with.
    lifecycle["scientific_readiness"]["failing_units"] = blockers["failing_units"]
    return lifecycle


def _revision_summary(revision: Mapping[str, Any]) -> dict:
    """One revision as a listing row. Never carries the stored document."""
    submission = revision.get("submission")
    return {
        "revision_no": revision["revision_no"],
        "revision_id": revision["revision_id"],
        "reason": revision["reason"],
        "created_utc": revision["created_utc"],
        "experiment_rev": revision["experiment_rev"],
        "content_signature": revision["content_signature"],
        "actor": _revision_actor(revision),
        "change_counts": revision.get("change_counts") or {},
        "submission": _submission_summary(submission),
    }


def _revision_actor(row: Mapping[str, Any]) -> dict:
    """WHO IS ON RECORD FOR THIS ROW — including, honestly, nobody.

    ``subject`` is returned verbatim and is ``None`` whenever ``trust_basis`` is
    ``unattributed``; the database enforces that pairing in both directions
    (``CHECK ((trust_basis = 'unattributed') = (subject IS NULL))``). No placeholder,
    no "system", no "unknown user", no deployment name — a name here would be a
    person credited with a declaration they did not make, which is the single worst
    thing this surface could invent.

    ``basis`` is passed through so a reader can see WHAT the attribution is worth.
    ``test_fixture`` is a real, shipped basis (``identity.FixtureEdgeVerifier`` mints
    a subject from the process environment) and it is **not proof anyone
    authenticated** — ``submission_store.capability`` already surfaces it on
    ``/api/health`` for that reason, and this does the same rather than flattening
    every attributed row into "attributed".
    """
    trust_basis = row.get("trust_basis")
    return {
        "subject": row.get("subject"),
        "trust_basis": trust_basis,
        "attributed": trust_basis != submissions.TRUST_BASIS_UNATTRIBUTED,
    }


def _submission_summary(submission: Mapping[str, Any] | None) -> dict | None:
    if submission is None:
        return None
    return {
        "submission_id": submission["submission_id"],
        "submitted_utc": submission["submitted_utc"],
        "unit_count": submission["unit_count"],
        "idempotency_key_used": submission["idempotency_key"] is not None,
        "actor": _revision_actor(submission),
        "conflict_summary": submission.get("conflict_summary") or {},
    }


def _history_unavailable(
    reason: str, message: str, body: dict, *, etag: str | None = None
) -> JSONResponse:
    """The typed ``503`` for "this deployment cannot read the submission history".

    503 FOR THE SAME REASON ``_submission_unavailable`` IS ONE: the request is well
    formed, the application is working, and a dependency this deployment is
    configured to use is not ready. Every reason it can carry is resolved by an
    operator action that is already specified.

    **THE BODY IS THE SAME ENVELOPE THE 200 CARRIES**, minus ``revisions`` and the
    counts. That is deliberate: a client reads one shape and branches on
    ``availability.state``, and cannot accidentally treat a refusal as a listing —
    the rows simply are not there to be misread as empty.

    ``etag`` IS TAKEN AND SET HERE BECAUSE FASTAPI WILL NOT DO IT. The list route
    sets ``response.headers["ETag"]`` on the injected ``Response``, but that only
    reaches a body FastAPI serialises itself; every refusal path returns a
    ``JSONResponse`` directly, and FastAPI does not merge the injected headers into
    one. So the ETag was silently dropped on exactly the paths this deployment
    always takes — ``tables_absent`` is its current state, so it was never emitted
    at all. The record's version is knowable on these paths (the experiment loaded
    fine; it is the HISTORY that could not be read), so withholding it was an
    accident rather than a policy.
    """
    response = JSONResponse(
        status_code=503,
        content={
            **body,
            "error": "revision_history_unavailable",
            "availability": _history_availability(_HISTORY_UNAVAILABLE, reason, message),
        },
    )
    if etag is not None:
        response.headers["ETag"] = etag
    return response


def _open_reader():
    """The revision reader for this deployment, or ``(None, reason, message)``.

    Returns ``(reader, None, None)`` when one exists. The gate is
    ``revision_history.reader``, which calls the SAME ``repo._postgres_available``
    the submission write path calls — so a deployment that cannot record a
    submission is exactly a deployment that cannot read one back.
    """
    selected = revision_history.reader()
    if selected is None:
        return None, submission_store.BLOCKER_NO_DURABLE_STORAGE, _HISTORY_NO_STORAGE_LEAD
    return selected, None, None


#: EVERY failure of a history read, not only the two the CONNECTION layer raises.
#:
#: This was ``(WriteRefused, MissingDependency)``. Those two are raised at exactly
#: four sites — the ``PGDATABASE`` gate, missing libpq environment,
#: ``psycopg2.connect`` failing, and a ``current_database()`` mismatch. **Nothing
#: wraps an exception raised by ``cursor.execute``.** ``db_write.write_transaction``
#: catches ``BaseException``, rolls back and re-raises unchanged, and ``create_app``
#: registers no catch-all handler.
#:
#: So the driver's own errors escaped as an undeclared **500** — exactly what the
#: note below says must never happen — on every reachable path that is not a
#: connection failure: the server dropping the connection mid-transaction, a
#: pooler rejecting ``SET LOCAL``, an administrator cancelling the query, a
#: ``lock_timeout`` firing, or a drifted ``0003`` in which ``to_regclass`` resolves
#: the relation but a column is missing (``_tables_present`` is relation-level and
#: cannot see that). The three tests that appeared to cover this raised
#: ``WriteRefused`` from a stub, so the gap was invisible.
#:
#: Worse than the status code: the raw psycopg2 exception reached the ASGI stack
#: and the log. ``connect_psycopg2`` strips those on the connect path precisely
#: because "psycopg2 messages echo the host, the user and the connection string";
#: the execute path had no equivalent guard. Only the exception CLASS is ever
#: reported here, never its message.
#:
#: ``Exception``, not ``BaseException``: a cancellation or ``KeyboardInterrupt``
#: must still propagate.
_HISTORY_READ_FAILURES = (Exception,)
#: ``MissingDependency`` IS CAUGHT HERE AND IS NOT CAUGHT BY ``post_submit``, AND
#: THE DIVERGENCE IS DELIBERATE RATHER THAN AN OVERSIGHT. It is raised when
#: ``PGHOST`` is set and psycopg2 is not importable — a deployment defect, not a
#: request defect — and on the write path it surfaces as a 500. **A read operation
#: in this application must never 500** (``_read_artifact_json``'s docstring states
#: the rule and gives the reason: the caller gets nothing usable, and in a bundled
#: `Promise.all` neither do its siblings). So these three GETs report the honest
#: "this deployment could not reach its database" instead. Making the write path
#: agree is a separate change with its own review; it is not silently made here.


#: What `availability.message` says when the history WAS read, on the operation
#: that returns a LIST. Present on the success path too, so a client never has to
#: treat a missing message as "everything is fine".
HISTORY_READ_NOTE = (
    "The submission history was read from this deployment's database. An empty list "
    "here means this record has no submitted revisions."
)

#: The same fact for the two operations that return ONE revision and a diff.
#:
#: `HISTORY_READ_NOTE` was served on all three, and its second sentence — "an
#: empty list here means this record has no submitted revisions" — is about a list
#: neither of those responses contains. Not user-visible today, because the UI
#: renders `availability.message` only on the non-available branches; a false
#: sentence in the contract's own response body all the same.
HISTORY_READ_NOTE_SINGLE = (
    "This revision was read from this deployment's database."
)


@router.get(
    "/experiments/{experiment_id}/revisions",
    tags=[TAG_EXPORT],
    summary="List a Record's Submitted Revisions",
    description=(
        "Lists the immutable snapshots captured when this record was submitted, "
        "newest first, and reports the record's derived submission lifecycle. "
        "Read-only: nothing here writes a revision, and the only writer of one is "
        "`POST /api/experiments/{experiment_id}/submit`.\n\n"
        "**`availability` is the field to read first, and an empty list is never a "
        "refusal.** The submission-history tables are created by a migration an "
        "operator applies separately from the image, so a running server can meet a "
        "database that does not have them. When that happens this operation answers "
        "`503` with `availability.state: \"unavailable\"` and **no `revisions` key "
        "at all** — never an empty list, because \"this record was never submitted\" "
        "and \"this server could not find out\" are different statements and only "
        "one of them was observed. `availability.reason` is `no_durable_storage`, "
        "`tables_absent` or `database_unavailable`; the three have three different "
        "remedies. A worked-example record answers `200` with "
        "`availability.state: \"not_applicable\"`, which is a fact rather than an "
        "inability: such records are never submitted.\n\n"
        "`lifecycle.state` is DERIVED on every read and is never stored: `draft`, "
        "`needs_review`, `ready_to_submit` or `submitted`. `submitted` means a "
        "submission is on record for exactly the content this record holds NOW — it "
        "is never derived from whether the record was exported, which is a "
        "mechanical transform any caller can perform and is not a declaration by "
        "anyone. `lifecycle.submission.known` is `false` whenever the history could "
        "not be read, and the state then falls back to the scientific derivation "
        "rather than to `not submitted`.\n\n"
        "`lifecycle.submission_blocked_by_deployment` is reported SEPARATELY and "
        "never lowers `lifecycle.state`. A record whose science is finished reads "
        "`ready_to_submit` even where this deployment can accept no submission at "
        "all — which is every deployment shipped today, because no edge-trust "
        "verifier is configured and submission requires an attributable person.\n\n"
        "The listing is bounded; `total` is how many revisions EXIST, whatever the "
        "bounded list returned. No stored record snapshot is ever included."
    ),
    response_description=(
        "The record's submitted revisions newest first, how many exist, the derived "
        "lifecycle, and the availability of the history itself."
    ),
    responses={
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        **_R_REVISION_HISTORY_UNAVAILABLE,
    },
)
def list_revisions(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    response.headers["ETag"] = exp.etag()

    units = exp.export_units()
    signature = submissions.content_signature(exp.id, units)
    base = {
        "experiment_id": exp.id,
        "record_rev": exp.rev,
        "current_content_signature": signature,
        "signature_scope": submissions.SIGNATURE_SCOPE,
        "limit": revision_history.DEFAULT_REVISION_LIMIT,
    }

    def envelope(*, known: bool, submitted: bool | None, reason: str | None) -> dict:
        return {
            **base,
            "lifecycle": _lifecycle_payload(
                exp,
                units,
                submitted_known=known,
                submitted_for_current_content=submitted,
                unknown_reason=reason,
            ),
        }

    if scope is not None:
        # A FACT, NOT AN UNKNOWN — see `_HISTORY_WORKED_EXAMPLE_LEAD`. `submitted` is
        # reported as KNOWN and False because three independent enforcements make a
        # submission over a session record unreachable, and no database was consulted
        # to establish that.
        body = envelope(known=True, submitted=False, reason=None)
        body["availability"] = _history_availability(
            _HISTORY_NOT_APPLICABLE, "worked_example_session", _HISTORY_WORKED_EXAMPLE_LEAD
        )
        return body

    reader, reason, message = _open_reader()
    if reader is None:
        return _history_unavailable(
            reason, message, envelope(known=False, submitted=None, reason=reason),
            etag=exp.etag(),
        )
    try:
        read = reader.history(exp.id, signature)
    except _HISTORY_READ_FAILURES:
        return _history_unavailable(
            "database_unavailable",
            _HISTORY_DB_UNREACHABLE_LEAD,
            envelope(known=False, submitted=None, reason="database_unavailable"),
            etag=exp.etag(),
        )
    if not read["tables_present"]:
        return _history_unavailable(
            "tables_absent",
            _HISTORY_NO_TABLES_LEAD,
            envelope(known=False, submitted=None, reason="tables_absent"),
            etag=exp.etag(),
        )

    body = envelope(
        known=True, submitted=read["current_submission"] is not None, reason=None
    )
    body["availability"] = _history_availability(_HISTORY_AVAILABLE, None, HISTORY_READ_NOTE)
    body["revisions"] = [_revision_summary(r) for r in read["revisions"]]
    body["total"] = read["total"]
    body["returned"] = len(body["revisions"])
    body["current_submission"] = _submission_summary(read["current_submission"])
    return body


@router.get(
    "/experiments/{experiment_id}/revisions/{revision_no}",
    tags=[TAG_EXPORT],
    summary="Read One Submitted Revision",
    description=(
        "Returns one submitted revision of this record: when it was captured, who "
        "is on record for it, the run snapshots it holds, the field addresses that "
        "changed since the revision before it, and the submission that captured "
        "it. Read-only.\n\n"
        "**The stored record snapshot is deliberately NOT returned.** The revision "
        "holds a complete copy of the record as it was, and this operation reports "
        "what that revision IS rather than shipping the document; the field values "
        "themselves are available, scoped to what actually differs, from "
        "`GET .../revisions/{revision_no}/diff`.\n\n"
        "`actor.subject` is `null` and `actor.attributed` is `false` whenever the "
        "revision was recorded without an attributable person. No placeholder name "
        "is ever substituted. `actor.trust_basis` says what the attribution is "
        "worth: `test_fixture` is a real shipped basis and is **not** proof anyone "
        "authenticated.\n\n"
        "`changes` are the field addresses this revision differed from its "
        "PREDECESSOR at, exactly as they were recorded at submission time. They "
        "cover draft field values only — evidence entries, run overrides, answer "
        "logs and assets are not compared — so an empty list means no field value "
        "differed, never that nothing changed. A revision with no predecessor "
        "records no changes at all, which is not the same as having changed "
        "nothing.\n\n"
        "`503` with `availability.state: \"unavailable\"` when the history cannot be "
        "read; `404` when the record exists and holds no such revision number. Those "
        "are different answers and are never merged."
    ),
    response_description=(
        "The revision, its run snapshots, its recorded field-address changes, and "
        "the submission that captured it."
    ),
    responses={
        **_R_UNAUTHORIZED,
        **_R_REVISION_NOT_FOUND,
        **_R_REVISION_HISTORY_UNAVAILABLE,
    },
)
def get_revision(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    revision_no: Annotated[
        int,
        Path(ge=1, description="The revision number, as `GET .../revisions` reports it."),
    ],
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    base = {"experiment_id": exp.id, "revision_no": revision_no}

    if scope is not None:
        return {
            **base,
            "availability": _history_availability(
                _HISTORY_NOT_APPLICABLE,
                "worked_example_session",
                _HISTORY_WORKED_EXAMPLE_LEAD,
            ),
        }

    reader, reason, message = _open_reader()
    if reader is None:
        return _history_unavailable(reason, message, base, etag=exp.etag())
    try:
        read = reader.revision(exp.id, revision_no)
    except _HISTORY_READ_FAILURES:
        return _history_unavailable(
            "database_unavailable", _HISTORY_DB_UNREACHABLE_LEAD, base, etag=exp.etag()
        )
    if not read["tables_present"]:
        return _history_unavailable(
            "tables_absent", _HISTORY_NO_TABLES_LEAD, base, etag=exp.etag()
        )
    if read["revision"] is None:
        return _revision_not_found(exp.id, revision_no)

    revision = read["revision"]
    return {
        **base,
        "availability": _history_availability(_HISTORY_AVAILABLE, None, HISTORY_READ_NOTE_SINGLE),
        # Built field by field. `revision["state"]` — the stored record snapshot — is
        # never named here, and `test_revision_history` asserts the body has no
        # `state` key on any path.
        "revision": {
            **_revision_summary(revision),
            "run_revisions": revision["run_revisions"],
            "changes": revision["changes"],
            "changes_scope": _REVISION_CHANGES_SCOPE,
            "submission_runs": revision["submission_runs"],
        },
    }


#: What the recorded change rows cover, echoed into the response so a reader never
#: has to infer a comparison's scope from its name. It is the scope
#: `submissions.field_values` documents and `0003_revisions.sql` writes down.
_REVISION_CHANGES_SCOPE = "draft_field_values_only"


def _revision_not_found(experiment_id: str, revision_no: int) -> JSONResponse:
    """``404`` for a revision number this record does not have.

    SEPARATE FROM ``experiment_not_found`` and separate from the ``503``. The record
    was read successfully and the history was read successfully; there is simply no
    revision under that number. Collapsing it into either of the others would tell a
    client to go looking in the wrong place — the same reasoning ``_run_not_found``
    already applies to a run id on a record that exists.
    """
    return JSONResponse(
        status_code=404,
        content={
            "error": "revision_not_found",
            "experiment_id": experiment_id,
            "revision_no": revision_no,
            "message": (
                "This record's submission history was read and holds no revision "
                f"{revision_no}."
            ),
        },
    )


@router.get(
    "/experiments/{experiment_id}/revisions/{revision_no}/diff",
    tags=[TAG_EXPORT],
    summary="Compare the Current Record Against a Submitted Revision",
    description=(
        "Compares the record AS IT IS NOW against the immutable snapshot captured "
        "by one submitted revision, and reports every draft field address whose "
        "value differs, with the value on each side. Read-only.\n\n"
        "**The comparison is narrow, and it says so in `changes_scope`.** Only "
        "draft field values are compared — the same scope the stored change rows "
        "use. Evidence entries, run overrides, answer logs, assets and implicit "
        "claims are NOT compared, and neither is anything nested inside a value "
        "beyond that value's canonical form. An empty `changes` list therefore "
        "means no field value differed; it does not mean nothing changed.\n\n"
        "`content_signature_matches` is the stronger, authoritative statement and "
        "covers more than `changes` does: it is `true` only when this record's "
        "current content signature equals the one the revision recorded. **An empty "
        "`changes` list beside `content_signature_matches: false` is a real and "
        "meaningful state** — it means something outside draft field values differs, "
        "and this operation is telling you it did not look there.\n\n"
        "`units` reports which export units (runs, or the record itself when it has "
        "none) were added and removed, separately from the field changes. A removed "
        "run also contributes one `removed` field row per value it held, so the two "
        "describe the same event at two altitudes.\n\n"
        "`comparable` is `false` when the stored snapshot could not be read back "
        "into a comparable record. `changes` is then absent rather than empty, "
        "because an empty list would assert a comparison this server did not make."
    ),
    response_description=(
        "The field-level differences between the current record and the named "
        "revision, the unit membership changes, and whether the content signatures "
        "match."
    ),
    responses={
        **_R_UNAUTHORIZED,
        **_R_REVISION_NOT_FOUND,
        **_R_REVISION_HISTORY_UNAVAILABLE,
    },
)
def get_revision_diff(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    revision_no: Annotated[
        int,
        Path(ge=1, description="The revision number, as `GET .../revisions` reports it."),
    ],
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    units = exp.export_units()
    signature = submissions.content_signature(exp.id, units)
    base = {
        "experiment_id": exp.id,
        "revision_no": revision_no,
        "record_rev": exp.rev,
        "current_content_signature": signature,
        "changes_scope": _REVISION_CHANGES_SCOPE,
    }

    if scope is not None:
        return {
            **base,
            "availability": _history_availability(
                _HISTORY_NOT_APPLICABLE,
                "worked_example_session",
                _HISTORY_WORKED_EXAMPLE_LEAD,
            ),
        }

    reader, reason, message = _open_reader()
    if reader is None:
        return _history_unavailable(reason, message, base, etag=exp.etag())
    try:
        read = reader.revision(exp.id, revision_no)
    except _HISTORY_READ_FAILURES:
        return _history_unavailable(
            "database_unavailable", _HISTORY_DB_UNREACHABLE_LEAD, base, etag=exp.etag()
        )
    if not read["tables_present"]:
        return _history_unavailable(
            "tables_absent", _HISTORY_NO_TABLES_LEAD, base, etag=exp.etag()
        )
    if read["revision"] is None:
        return _revision_not_found(exp.id, revision_no)

    revision = read["revision"]
    # THE ONE DEFINITION OF "REHYDRATE A STORED SNAPSHOT INTO COMPARABLE DRAFTS", and
    # it is REUSED rather than copied even though it is module-private. It is what
    # the submit path itself compares against, its `None`-on-unreadable tolerance is
    # load-bearing (a historical row that cannot be read must degrade the comparison,
    # never fail the request), and a second copy here could diverge from the baseline
    # the stored change rows were computed against — which would put two different
    # answers to one question on two screens.
    previous_units = submission_store._previous_unit_drafts(revision.get("state"))
    current_units = submissions.units_by_id(units)
    comparable = previous_units is not None

    body = {
        **base,
        "availability": _history_availability(_HISTORY_AVAILABLE, None, HISTORY_READ_NOTE_SINGLE),
        "comparable": comparable,
        "content_signature_matches": (
            revision["content_signature"] == signature
        ),
        "revision": {
            **_revision_summary(revision),
            "run_labels": {
                r["run_id"]: r["label"]
                for r in revision["run_revisions"]
                if r["label"] is not None
            },
        },
    }
    if not comparable:
        body["comparable_note"] = (
            "The snapshot stored for this revision could not be read back into a "
            "comparable record, so no field comparison was made. The revision "
            "itself, and the change addresses recorded when it was submitted, are "
            "unaffected."
        )
        body["units"] = submissions.unit_membership_changes(None, current_units)
        return body

    changes = submissions.address_value_changes(previous_units, current_units)
    body["changes"] = changes
    body["change_counts"] = {
        kind: sum(1 for c in changes if c["change_kind"] == kind)
        for kind in submissions.CHANGE_KINDS
    }
    body["units"] = submissions.unit_membership_changes(previous_units, current_units)
    body["current_run_labels"] = {
        unit.run_id: unit.run_label for unit in units if unit.run_id is not None
    }
    return body


# --- 8b. CSV ingestion preview (P31.1 — read-only, no mutation) ---------------


def _csv_error(err: csv_ingest.CsvIngestError) -> JSONResponse:
    """Serialize a typed CSV-ingress rejection (stable code, never a stack)."""
    return JSONResponse(
        status_code=err.http_status,
        content={"error": err.code, "message": err.message},
    )


async def _read_bounded_body(request: Request, max_bytes: int) -> bytes:
    """Accumulate the raw request body from ``request.stream()``, BOUNDED.

    Aborts with a typed ``request_too_large`` (413) the moment the running total
    exceeds ``max_bytes`` — the full body is NEVER allocated when oversized, and
    nothing is spooled to disk (no multipart, no ``SpooledTemporaryFile``, no temp
    file). Genuinely all-in-memory by construction.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise csv_ingest.CsvIngestError(
                "request_too_large",
                413,
                f"The body exceeds the {max_bytes}-byte limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/experiments/{experiment_id}/ingestion/csv/preview",
    tags=[TAG_INGESTION],
    summary="Preview a Campaign-Sheet CSV Against a Record",
    description=(
        "Read-only preview of a campaign-sheet CSV, reconciled field by field "
        "against this record's current authoritative values. Returns the row and "
        "candidate counts, the mapped candidate fields with their reconciliation "
        "outcome, and non-actionable warnings for unrecognised columns.\n\n"
        "Send the CSV as a raw `text/csv` request body, not as a multipart form. "
        "The body is read in memory under a hard size limit and is never written "
        "anywhere: no draft change, no revision bump, no export, no indexing, and "
        "no retained upload. Only outcome metadata is logged — never the rows, the "
        "candidate values, or the filename.\n\n"
        "Requires the record's current `ETag` in `If-Match`, which is checked "
        "before the body is read. Available only while the deployment is in "
        "synthetic-only data mode.\n\n"
        "A malformed CSV — unreadable, an empty or duplicated header column, a "
        "missing required column, or a row, column, cell, or candidate count over "
        "the limit — is rejected with `422` and a stable error code."
    ),
    response_description=(
        "The typed preview: counts, reconciled candidate fields, and warnings. "
        "Nothing was changed."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        **_R_PRECONDITION,
        # Deliberately overrides the shared 400 above: on this route a 400 has two
        # distinct causes, and the caller needs to know both.
        400: {
            "description": (
                "Either the `If-Match` header is not one or more strong quoted "
                "validators, or the body is empty, is not valid UTF-8, or contains "
                "a NUL byte."
            )
        },
        403: {
            "description": (
                "The deployment is not in synthetic-only data mode, so this "
                "preview path is refused. Nothing was read."
            )
        },
        413: {
            "description": (
                "The body exceeds the request size limit. The read is aborted the "
                "moment the limit is passed, so an oversized body is never fully "
                "held in memory and is never spooled to disk."
            )
        },
    },
)
async def post_csv_preview(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    request: Request,
    response: Response,
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The record's current `ETag`, checked before the body is "
            "read."
        ),
    ),
    x_filename: str | None = Header(
        default=None,
        alias="X-Filename",
        description=(
            "Optional display name for the CSV, used only for evidence "
            "attribution in the preview. It is sanitised to a bare filename and is "
            "never used as a filesystem path, a record id, or a value."
        ),
    ),
):
    """READ-ONLY typed preview of an uploaded campaign-sheet CSV (P31.1).

    Accepts a RAW ``text/csv`` body (NOT multipart), bounded in-memory. Order:
    auth (middleware) -> runtime-mode synthetic-only -> experiment 404 -> If-Match
    (428/412/400) -> bounded body read (413) -> utf-8-sig decode (empty/NUL/invalid
    -> typed) -> CSV v1 validate (typed) -> in-memory FIELD_MAP parse -> typed
    preview. Performs NO mutation: no Workspace write, no rev bump, no export, no
    retrieval/Project-Memory indexing, no persisted upload. Logs metadata only.
    """
    # Runtime-mode gate: this synthetic preview path is refused outside
    # synthetic-only mode (fail-closed; the app also refuses to boot in real mode).
    if not runtime_mode.is_synthetic_only():
        _log.info("csv_preview outcome=runtime_mode_denied experiment=%s", experiment_id)
        return JSONResponse(
            status_code=403,
            content={
                "error": "runtime_mode_denied",
                "message": "CSV preview is available only in synthetic-only mode.",
            },
        )
    # Existence BEFORE If-Match (an unknown id 404s regardless of headers).
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        _log.info("csv_preview outcome=experiment_not_found experiment=%s", experiment_id)
        return _not_found(experiment_id)
    # Version binding: current ETag required (missing -> 428, malformed -> 400,
    # stale -> 412). Evaluated BEFORE the body is read so a stale client refreshes
    # without us consuming a (potentially large) body.
    err = _check_if_match(if_match, exp)
    if err is not None:
        _log.info("csv_preview outcome=precondition experiment=%s", experiment_id)
        return err

    started = datetime.now(timezone.utc)
    source_name = csv_ingest.safe_source_name(x_filename)
    # P31.2 — build the CURRENT authoritative record view (READ-ONLY) the
    # reconciliation compares against: official path -> {value, P28 classification}.
    _values = {e["path"]: e["value"] for e in serialize.evidence_trail_from_draft(exp.draft)}
    _classes = {r["field"]: r["classification"] for r in evidence_classify.classify_fields(exp.draft)}
    record_fields = {
        path: {"value": v, "classification": _classes.get(path)}
        for path, v in _values.items()
    }
    try:
        raw = await _read_bounded_body(request, csv_ingest.MAX_BODY_BYTES)
        text = csv_ingest.decode_body(raw)
        preview = csv_ingest.build_preview(
            text,
            source_name=source_name,
            source_record_rev=exp.rev,
            experiment_id=experiment_id,
            record_fields=record_fields,
        )
    except csv_ingest.CsvIngestError as e:
        # Metadata only — never the raw body / rows / candidate values / filename.
        _log.info("csv_preview outcome=rejected code=%s experiment=%s", e.code, experiment_id)
        return _csv_error(e)

    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    _log.info(
        "csv_preview outcome=ok experiment=%s bytes=%d rows=%d candidates=%d duration_ms=%d",
        experiment_id,
        len(raw),
        preview["row_count"],
        preview["candidate_count"],
        duration_ms,
    )
    # Read-only: rev is unchanged; echo the current validator for convenience.
    response.headers["ETag"] = exp.etag()
    return preview


def _validate_unit(unit: ws.ExportUnit) -> dict:
    """One export unit's official-schema verdict, ADDRESSED TO ITS RUN.

    ``dry_run`` is per unit and states WHICH document was checked: the written record
    when this unit is materialised, an in-memory candidate otherwise. A flat verdict
    over N records would not be readable — three runs can produce the same message
    and a caller could not tell which to open — so this mirrors the export route's
    ``_unit_result_entry``.

    ``official_validator_ran`` IS THE DISCRIMINATOR THE COMMENT BELOW ASKED FOR, and
    it is the whole point of this entry. It answers ONE question — *did
    ``isaac_records.official.validate_official`` examine the document these ``errors``
    describe?* — so a consumer never has to reconstruct the answer from ``dry_run``
    plus an ordering rule it had to read ``export.py`` to learn. It is derived HERE,
    at the route, from ``official_report is not None``; nothing in
    ``src/isaac_records/**`` changes, because that attribute already carries the fact
    faithfully (``export.py`` returns ``None`` at exactly the two returns that precede
    ``validate_official`` and at no other).

    IT DESCRIBES THE ``errors`` LIST BESIDE IT — not the unit, not the request. That
    is the ONE rule every producer and every consumer in this repository follows, and
    stating it as a property of the neighbouring list is what makes the aggregate in
    ``_fan_out_official_verdict`` derivable rather than a second convention.

    ``False`` IS NOT A VERDICT AND MUST NOT BE READ AS ONE. It says the vendored
    schema did not speak; ``CLAUDE.md`` §1 makes that schema not ours to speak for, so
    "it did not run" is the only honest thing to publish, and "it rejected the record"
    is the claim four surfaces made instead. On the two ``unavailable`` branches it is
    ``False`` as well — nothing ran there either — and ``unavailable`` remains the
    stronger, earlier-tested flag: no verdict at all, from any gate.

    IT MOVES NO VERDICT. ``ok`` is untouched on every branch, and ``CLAUDE.md`` §12's
    standing invariant — a warning or an ISAAC-local gate must never turn a PASS into a
    FAIL — is preserved by construction: this field is never read to compute ``ok``,
    here or anywhere downstream.
    """
    entry = {
        "run_id": unit.run_id,
        "run_label": unit.run_label,
        "record_id": unit.target_id,
    }
    if unit.materialised():
        record = _read_artifact_json(unit.record_path())
        if record is None:
            # Same fail-closed vocabulary as the single-record path: no verdict, not
            # a schema violation. `dry_run: false` — no dry run happened.
            #
            # `unavailable` MAKES THAT DISTINCTION MACHINE-READABLE, and it was added
            # because a client could not make it. The only signal used to be this
            # fixed English sentence inside `errors[0].message`, so the Run card
            # rendered "Check Failed" — a schema verdict — over a case this function
            # deliberately refuses to give a verdict on. `ok` stays False: the flag
            # explains the refusal, it does not soften it into a pass.
            return {
                **entry,
                "ok": False,
                "errors": [{"path": "$", "message": "Validation could not be completed."}],
                "dry_run": False,
                "unavailable": True,
                # The record could not be READ, so `validate_official` was never
                # reached. `dry_run: false` here means NO DRY RUN HAPPENED; without
                # this field a consumer branching on `dry_run` alone concluded the
                # written record had been checked by the official schema.
                "official_validator_ran": False,
            }
        report = validate_official(record, REPO_ROOT)
        return {
            **entry,
            "ok": report.ok,
            "errors": [{"path": e.path, "message": e.message} for e in report.errors],
            "dry_run": False,
            # The one branch that calls `validate_official` directly. `check_exactness`
            # does NOT run here, which is why the passing copy for a materialised unit
            # may not claim ISAAC's own gate.
            "official_validator_ran": True,
        }

    try:
        result = export_draft(unit.draft, REPO_ROOT)
    except Exception:
        _log.exception("validate dry-run failed run=%s", unit.run_id)
        return {
            **entry,
            "ok": False,
            "errors": [{"path": "$", "message": "Validation could not be completed."}],
            "dry_run": True,
            "unavailable": True,
            "official_validator_ran": False,
        }
    # THE OFFICIAL-SCHEMA CONFLATION, RECORDED WHERE IT IS MINTED — AND NOW CLOSED
    # ON THE WIRE. Kept in full rather than trimmed to the fix, because the shape of
    # the defect is what explains the shape of the field.
    #
    # These three branches produce THREE different kinds of finding under one key:
    #
    #   official_report is not None  -> the vendored official ISAAC schema's own verdict
    #   official_report is None      -> `export_draft` returned BEFORE `validate_official`
    #                                   ran, and `errors` are the no-guessing draft
    #                                   findings WITH ISAAC's anchored-pattern EXACTNESS
    #                                   findings folded in (see `export.py`)
    #
    # Measured over HTTP on a run whose descriptor `name` carries a trailing newline:
    #
    #   draft    {"ok": true, "errors": []}
    #   official {"ok": false, "dry_run": true, "schema": "ISAAC v1.05"}
    #            errors[0] = ISAAC's OWN exactness message
    #
    # A caller reading that has been told the official ISAAC schema rejected a record
    # the official ISAAC schema never examined. `CLAUDE.md` §12 states the rule
    # directly — *"the gate is ISAAC's, not upstream's ... no surface may report an
    # exactness refusal as an official-schema error"* — and `_export_step_detail`
    # already closed exactly this defect one wire over.
    #
    # WHY FOUR SURFACES GOT IT WRONG AT ONCE, which is the part this field fixes:
    # ~~THERE IS NOTHING ON THE PAYLOAD TO BRANCH ON.~~ `schema` is stamped
    # unconditionally by the two callers, and `dry_run` does not discriminate — a
    # dry-run PASS does require `validate_official`, while a dry-run FAILURE may never
    # have reached it. So no client, however careful, could tell the two apart, and
    # every one of them had to remember an ordering rule it could only learn by
    # reading `export.py`. THAT is why "fix the surfaces" recurred four times: the
    # remedy was unbounded by construction, one file per consumer, forever.
    #
    # ~~"THE DURABLE FIX IS A DISCRIMINATOR ON THE WIRE — an `official_validator_ran`
    # boolean ... It is deliberately NOT done here"~~ — **DONE.** The three branches
    # below now publish `official_validator_ran`, and every consumer branches on it
    # instead of on an ordering rule. The strikethroughs above are deliberate: this
    # comment named its own remedy and deferred it, and a reader who remembers the
    # deferral needs to see that it was discharged rather than find a comment that
    # reads as though the field were always there.
    #
    # THE ALTERNATIVE THAT WAS NOT TAKEN, and why. `POST /api/validate/record` splits
    # its findings into `errors` and `exactness_errors`. Splitting them here too would
    # be a BREAKING change to two published operations' `errors` key and would still
    # not separate the no-guessing findings from the exactness ones — `export.py`
    # folds those together into `draft_report` upstream of this function, so the wire
    # this reads cannot tell them apart either (`_export_step_detail` records the same
    # limit). One added boolean answers the question every consumer actually asks —
    # *may I name the official schema?* — without moving a single existing key, and
    # without this route claiming to know which of ISAAC's own two gates refused.
    if result.official_report is not None:
        errors = [
            {"path": e.path, "message": e.message} for e in result.official_report.errors
        ]
    elif not result.draft_report.ok:
        errors = [{"path": w, "message": m} for w, m in result.draft_report.errors]
    else:
        errors = []
    return {
        **entry,
        "ok": result.ok,
        "errors": errors,
        "dry_run": True,
        # THE THREE BRANCHES ABOVE COLLAPSE TO THIS ONE BOOLEAN, which is why no
        # client has to re-derive them: the first is the official schema's own verdict
        # and the other two are not.
        "official_validator_ran": result.official_report is not None,
    }


def _fan_out_official_verdict(exp: Experiment) -> dict:
    """The official-schema verdict for an experiment WITH RUNS. One definition.

    REVIEW ITEM F1 — THE C6 FIX REPAIRED ONE OF TWO COPIES. C6 made ``post_validate``
    fan-out aware, and ``_assistant_validate_dryrun`` — reached from the Assistant Q&A
    route — carried the identical defect untouched: it tested ``exp.exported()``,
    permanently False for a fan-out, and validated ``exp.draft``, the experiment-level
    half that is never exported and is not a record. Measured on ``c467dc7``, one
    process, one fully-exported 2-run fan-out::

        /api/experiments/{id}/validate         -> ok: true
        routes._assistant_validate_dryrun(exp) -> {"ok": false, "errors":
           [{"path": "$", "message": "'descriptors' is a required property"}]}

    That error string is verbatim the defect C6 was written to remove. So this is not
    fixed twice: it is ONE function, called from both, and a third divergence would
    have to be introduced deliberately.

    It returns ``post_validate``'s whole response body rather than a smaller shared
    core, because that endpoint is the one that OWNS this contract; the assistant
    projects the two keys it answers with. The reverse — a lowest-common-denominator
    return that each caller re-wraps — would have left the ``runs``/``dry_run``
    aggregation duplicated, which is the half that was actually wrong.

    ``dry_run`` at the top level is true if ANY unit's verdict came from an in-memory
    candidate: ``dry_run: false`` is the strong claim that a WRITTEN record was
    checked, and it must not be made on behalf of a unit that has no written record.

    ``official_validator_ran`` AT THE TOP LEVEL DESCRIBES THE TOP-LEVEL ``errors``,
    and that is the only aggregation rule that is derivable rather than invented.
    ``errors`` here is the FIRST FAILING unit's list, so the flag is that unit's flag;
    a different rule (``any``/``all`` over the units) would describe a set the
    ``errors`` key does not carry, and a caller rendering those errors would once
    again be reasoning about a document other than the one in front of it.

    On a PASS the two candidate rules agree, so nothing hangs on the choice: a unit's
    ``ok`` is reachable only through ``export.py``'s single ``ok=True`` return, which
    sits after ``validate_official`` has run and passed, so every unit's flag is
    ``True``. The empty-``entries`` case is written out rather than left to
    ``all(())`` — which is ``True`` — because "no unit exists" must not publish that
    the official validator ran.

    ``unavailable`` FOLLOWS THE SAME RULE AND FOR THE SAME REASON. It is the first
    failing unit's flag, because ``errors`` is that unit's list; and it is OMITTED
    rather than published as ``False``, matching ``_validate_unit``, so a caller reads
    its presence as the exceptional claim it is. Without it, a fan-out whose first
    failing unit could not be READ would publish ``official_validator_ran: false``
    alone — indistinguishable from ISAAC's export gate having refused, which is a
    different and untrue statement.
    """
    entries = [_validate_unit(unit) for unit in exp.export_units()]
    failed = [entry for entry in entries if not entry["ok"]]
    body = {
        "ok": not failed,
        # The FIRST FAILING unit's errors, so a caller reading only `errors` is shown
        # an actual failure; every unit's own verdict is in `runs`.
        "errors": failed[0]["errors"] if failed else [],
        "schema": SCHEMA_LABEL,
        "dry_run": any(entry["dry_run"] for entry in entries),
        "official_validator_ran": (
            bool(failed[0]["official_validator_ran"])
            if failed
            else bool(entries) and all(e["official_validator_ran"] for e in entries)
        ),
        "runs": entries,
    }
    if failed and failed[0].get("unavailable") is True:
        body["unavailable"] = True
    return body


# --- 9. validate --------------------------------------------------------------


@router.post(
    "/experiments/{experiment_id}/validate",
    tags=[TAG_VALIDATION],
    summary="Validate a Record Against the Official Schema",
    description=(
        "Runs this record through the export gate and returns `ok`, a list of "
        "`{path, message}` findings, the schema label, and whether the check was a "
        "dry run.\n\n"
        "**`errors` is the vendored official ISAAC schema's verdict WHERE THE "
        "OFFICIAL VALIDATOR RAN — and otherwise the findings that stopped the export "
        "before it could.** `official_validator_ran` SAYS WHICH, and it is the field "
        "to branch on: `true` means the official validator examined the document "
        "these `errors` describe, `false` means the export was refused before it was "
        "reached — by the no-guessing draft check, or by ISAAC's own anchored-pattern "
        "exactness gate, which refuses a value that satisfies "
        "one of the schema's `^...$` patterns only because Python's `$` also matches "
        "before a trailing newline. Those findings arrive here under the same "
        "`errors` key, so a failing verdict is not by itself evidence that the "
        "official schema rejected anything — and `dry_run` does not answer it, "
        "because a dry-run PASS does require official validation while a dry-run "
        "FAILURE may never have reached it. `official_validator_ran: false` is NOT a "
        "verdict: it says the vendored schema did not speak, never that it refused. "
        "`schema` names the schema this "
        "deployment would validate against; it is stamped on every response and is "
        "not a claim that the schema produced the findings beside it. **`POST /api/validate/record` "
        "reports the two gates separately (`schema_ok` and `exactness_errors`) and "
        "is the operation to use when the distinction matters.**\n\n"
        "For an already-exported record the written record is validated "
        "(`dry_run: false`). Otherwise the export is run in memory and the "
        "resulting candidate record is validated without writing anything "
        "(`dry_run: true`). Read-only in both cases. The verdict comes from the "
        "same deterministic core function the command line uses.\n\n"
        "A record with **runs** exports one official record per run, so it is "
        "checked per run: `runs[]` carries each run's own verdict, its errors, its "
        "own `dry_run` and its own `official_validator_ran`, and the top-level `ok` "
        "is true only when every run "
        "passes. The top-level `dry_run` is `true` if any run's verdict came from "
        "an in-memory candidate rather than a written record. The top-level "
        "`official_validator_ran` describes the top-level `errors` — which are the "
        "FIRST FAILING run's — so it is that run's flag; when nothing failed it is "
        "`true`, because a passing verdict is only reachable through the official "
        "validator. Read a run's own flag for a run's own errors.\n\n"
        "If the written record cannot be read at all, no verdict is invented: the "
        "operation reports `ok: false`, the fixed error `Validation could not be "
        "completed.`, `dry_run: false`, `official_validator_ran: false`, and "
        "**`unavailable: true`** — at the TOP LEVEL as well as on a run entry, and "
        "the top-level flag is present whenever the first failing run carries it. "
        "Read that as *no verdict*, not as a schema violation — the artifacts "
        "operation reports why the file could not be read. `unavailable` was added "
        "because the fixed English sentence was the only signal, and a client that "
        "matched on `ok` alone rendered a non-verdict as a schema failure; the "
        "top-level `ok` deliberately stays `false` either way, so the flag explains "
        "the refusal without softening it. **`official_validator_ran: false` alone "
        "does not distinguish these two**: ISAAC's own export gate refusing and "
        "nothing running at all both report it, so read `unavailable` first. It is "
        "absent on every verdict that IS a verdict."
    ),
    response_description=(
        "The verdict, its errors, whether it was a dry run, whether the official "
        "validator produced the errors beside it, and — when nothing produced a "
        "verdict at all — `unavailable`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def post_validate(scope: TutorialScopeDep, experiment_id: ExperimentId):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)

    if exp.runs:
        # REVIEW ITEM C6 — this branch used not to exist, and its absence produced a
        # FALSE NEGATIVE about the official schema. `exp.exported()` is None-backed
        # for a fan-out, so a fully-exported fan-out fell into the dry-run branch
        # below and validated `exp.draft` — the EXPERIMENT-LEVEL HALF, which is never
        # exported and is not a record. Measured on `f7c286c` moments after all N
        # records passed official validation:
        #
        #     {"ok": false, "errors": [{"path": "$",
        #      "message": "'descriptors' is a required property"}], "dry_run": true}
        #
        # It is made fan-out aware rather than made to refuse, because the honest
        # answer IS computable from the same core function, and "Validation could not
        # be completed" would be a weaker statement than the truth. The aggregate is
        # ALL units, matching the export gate (contract §3 D4).
        #
        # `dry_run` at the top level is true if ANY unit's verdict came from an
        # in-memory candidate. `dry_run: false` is the strong claim that the WRITTEN
        # record was checked, and it must not be made on behalf of a unit that has no
        # written record; `runs[]` carries the per-unit answer.
        #
        # REVIEW ITEM F1 — the body is built by `_fan_out_official_verdict`, which the
        # assistant's validate thunk also calls. It used to be inline here, and the
        # assistant kept its own pre-C6 copy.
        return _fan_out_official_verdict(exp)

    if exp.exported():
        # P4 review FIX C — read DEFENSIVELY. The state can say exported while the
        # artifact is absent or corrupt (a fault in export's artifact->sidecar->state
        # window, or an out-of-band deletion), and an unguarded read raised
        # `FileNotFoundError` -> an unhandled 500 with the absolute server path in the
        # server log. The frontend `getExportReadiness` fetches this in the SAME
        # `Promise.all` as `/artifacts`, so one raise took the whole readiness view
        # down no matter how well the other responses degraded.
        record = _read_artifact_json(exp.record_path())
        if record is None:
            # FAIL CLOSED, and reuse the EXISTING crash-sentinel vocabulary rather
            # than inventing a message. `ok: true` here would be a false claim of
            # validity about a record that could not even be read, and falling back to
            # a dry run would silently change the SUBJECT of the verdict from the
            # written artifact to an in-memory candidate. `Validation could not be
            # completed.` is the one message `assistant_paths.is_validation_unavailable`
            # (and its TypeScript twin `isValidationUnavailable`) already recognises as
            # "the validator did not run", so both readers say so instead of rendering
            # "1 record-level validation issue" for a violation nobody located. The
            # artifact-specific reason is single-sourced in `/artifacts`
            # (`dependencies.MISSING_REASON`), which is the endpoint that describes
            # files; this one describes verdicts. `dry_run: false` is accurate: no dry
            # run happened.
            _log.warning(
                "validate: record %s is marked exported but its artifact could not be "
                "read; reporting no verdict",
                exp.id,
            )
            return {
                "ok": False,
                "errors": [{"path": "$", "message": "Validation could not be completed."}],
                "schema": SCHEMA_LABEL,
                "dry_run": False,
                # Nothing was validated: the artifact could not be read. `dry_run:
                # false` here means NO DRY RUN HAPPENED, which is why this flag has
                # to be stated separately rather than inferred from it.
                "official_validator_ran": False,
                # `unavailable` AT THE TOP LEVEL, AND IT WAS MISSING HERE WHILE
                # `_validate_unit` HAS SET IT ON THE EQUIVALENT BRANCH ALL ALONG.
                #
                # Measured over HTTP on an exported record whose artifact was deleted
                # out of band, BEFORE this line existed:
                #
                #   {"ok": false, "schema": "ISAAC v1.05", "dry_run": false,
                #    "official_validator_ran": false,
                #    "errors": [{"path": "$", "message":
                #                "Validation could not be completed."}]}
                #
                # `official_validator_ran: false` is TRUE of that payload and is not
                # enough, because it is the same shape ISAAC's own export gate returns
                # — so a client that reads "the validator did not run" concludes "a
                # GATE refused", and NO gate refused: the file could not be opened.
                # Adding the discriminator without this one would have replaced one
                # false attribution with a different false attribution.
                #
                # The three keys answer three different questions and none substitutes
                # for another: `dry_run` names the DOCUMENT, `official_validator_ran`
                # names the SOURCE of the findings, `unavailable` says there is no
                # verdict from any source. `ok` stays False on all of them.
                "unavailable": True,
            }
        report = validate_official(record, REPO_ROOT)
        return {
            "ok": report.ok,
            "errors": [{"path": e.path, "message": e.message} for e in report.errors],
            "schema": SCHEMA_LABEL,
            "dry_run": False,
            "official_validator_ran": True,
        }

    # Dry-run: export_draft in memory (writes nothing). Robust to malformed drafts.
    try:
        result = export_draft(exp.draft, REPO_ROOT)
        if result.official_report is not None:
            errors = [
                {"path": e.path, "message": e.message}
                for e in result.official_report.errors
            ]
        elif not result.draft_report.ok:
            errors = [
                {"path": w, "message": m} for w, m in result.draft_report.errors
            ]
        else:
            errors = []
        ok = result.ok
        # Same derivation as `_validate_unit`, from the same attribute, describing the
        # same list. Kept beside the branch that produced `errors` rather than
        # recomputed below, so the two can never disagree about which list they mean.
        official_validator_ran = result.official_report is not None
        unavailable = False
    except Exception:
        # Defensive: never 500, and never interpolate the exception (path/stack/
        # secret) into the client response. Return a fixed, path-free message and
        # log the real detail server-side for operators.
        _log.exception("validate dry-run failed experiment=%s", experiment_id)
        ok, errors = False, [{"path": "$", "message": "Validation could not be completed."}]
        official_validator_ran = False
        # NO VERDICT FROM ANY GATE — the same claim `_validate_unit` already makes on
        # its own exception branch, and for the same reason: a caller must not read
        # "the official validator did not run" as "one of ISAAC's gates refused".
        unavailable = True

    body = {
        "ok": ok,
        "errors": errors,
        "schema": SCHEMA_LABEL,
        "dry_run": True,
        "official_validator_ran": official_validator_ran,
    }
    # ABSENT ON EVERY VERDICT THAT IS A VERDICT, exactly as on the run entries. A key
    # that is always present and usually `false` invites a client to treat it as part
    # of the verdict; absence is what makes "there is no verdict here" the exceptional
    # reading it should be.
    if unavailable:
        body["unavailable"] = True
    return body


# --- 9b. standalone validator (P36.3, Governance & Safety) ---------------------

# Bounded before parse: a JSON candidate record is a small document, and this
# keeps the whole request in memory deterministically (never spooled to disk).
MAX_VALIDATE_RECORD_BYTES = 512 * 1024


@router.post(
    "/validate/record",
    tags=[TAG_VALIDATION],
    summary="Validate a Supplied Candidate Record",
    description=(
        "Standalone validator for a candidate official ISAAC record supplied "
        "directly as a JSON request body — no experiment, no draft, and no "
        "workspace involved. Returns `ok`, the official schema's own `schema_ok`, "
        "a rendered summary line, the `{path, message}` schema errors, the "
        "separately-listed `exactness_errors`, the schema version checked "
        "against, and `warnings`.\n\n"
        "**Two gates, reported separately.** `schema_ok` and `errors` are the "
        "vendored official schema's verdict, produced by the same authoritative "
        "validator the per-experiment validation operation calls — those agree by "
        "construction. `ok` is narrower: it is `schema_ok` AND ISAAC's "
        "anchored-pattern exactness gate, which refuses a value that satisfies one "
        "of the schema's `^...$` patterns only because Python's `$` also matches "
        "before a trailing newline. That gate is ISAAC's own, not the official "
        "schema's, so its findings are listed in `exactness_errors` and are never "
        "merged into `errors`.\n\n"
        "**A correction, kept visible.** This description used to say that this "
        "operation and the per-experiment one 'agree by construction', full stop. "
        "That is true of the schema verdict and false of the top-level `ok`, which "
        "is why the sentence is now scoped. This operation is the stricter of the "
        "two: `export_draft` applies the exactness gate, so the per-experiment "
        "operation applies it on its dry-run branch, while validating an "
        "ALREADY-EXPORTED record reports the schema verdict alone. A record "
        "carrying such a value therefore reads `ok: false` here and `ok: true` "
        "there. Read `schema_ok` to ask whether the official schema accepts the "
        "record, and `ok` to ask whether ISAAC would export it.\n\n"
        "`warnings` is the same advisory tier the per-record warnings operation "
        "serves, run over the supplied document. It is ADVISORY and NON-GATING, "
        "and that is unchanged by the exactness gate above: a warning can never "
        "turn a pass into a failure, and this operation is never a second "
        "authority on validity beside the vendored schema. **A second correction, "
        "also kept visible:** this paragraph used to add 'so `ok` is computed from "
        "the schema verdict alone'. The non-gating claim about WARNINGS is still "
        "exactly true; the clause it leaned on is not, because `ok` now also "
        "carries the exactness gate. The two are independent — warnings never move "
        "`ok`, and exactness always can.\n\n"
        "The body is never written anywhere and its content is never logged; only "
        "the outcome, error count and warning count are.\n\n"
        "Send the record as a raw JSON body. The body is read in memory under a "
        "hard size limit."
    ),
    response_description=(
        "The official-schema verdict, a rendered summary, the errors, and the "
        "advisory warnings — which carry no verdict of their own."
    ),
    responses={
        **_R_UNAUTHORIZED,
        413: {
            "description": (
                "The body exceeds the request size limit. The read is aborted the "
                "moment the limit is passed."
            )
        },
        422: {
            "description": (
                "The body is not well-formed JSON, or it is valid JSON but not a "
                "JSON object. Nothing was validated."
            )
        },
    },
)
async def post_validate_record(request: Request):
    """Standalone validator: paste/upload a candidate official ISAAC record and
    check it against the vendored schema — no experiment, no draft, no workspace.

    REUSES the same authoritative ``isaac_records.official.validate_official``
    (over the same ``REPO_ROOT``-resolved schema) that ``post_validate`` above
    calls for exported records — SCHEMA-verdict parity is by construction (same
    function, same schema), not a second reimplementation.

    THAT PARITY IS NARROWER THAN IT USED TO BE, AND THE OLD WORDING SAID SO TOO
    BROADLY. It read "verdict parity is by construction"; that now holds of
    ``schema_ok``/``errors`` and NOT of the top-level ``ok``, because this route
    also applies ``check_exactness`` and ``post_validate``'s already-exported
    branch does not (its dry-run branch does, through ``export_draft``). MEASURED
    divergence on a record whose ``tags`` entry ends in a newline: ``ok: false``
    here, ``ok: true`` there.

    That divergence is DELIBERATE HERE and is a REPORTED FINDING THERE, and this
    slice does not change ``post_validate``. Deliberate here: this route answers
    "is this candidate good?" about a record nobody has exported, and answering
    yes to something ``export_draft`` refuses would make the standalone validator
    the one surface that contradicts the product. A finding there: an exported
    artifact written BEFORE this gate existed, or edited out of band, can hold
    such a value and ``post_validate`` will report it clean while ``isaac validate
    --official`` on the same bytes exits 1. Closing that means deciding whether an
    immutable already-written record should be re-judged by a rule that postdates
    it — a scope decision, not a side effect of this change.

    Read-only and side-effect-free: the body is never written anywhere (no
    workspace file, no temp file, no record mutation), and nothing about its
    content is logged — only outcome metadata (ok/error-count), matching the
    csv-preview route's logging discipline just above.
    """
    try:
        raw = await _read_bounded_body(request, MAX_VALIDATE_RECORD_BYTES)
    except csv_ingest.CsvIngestError as e:
        # _read_bounded_body's overflow guard is generic (code/status/message);
        # reused here purely for its bounded, never-spooled read loop.
        _log.info("validate_record outcome=rejected code=%s", e.code)
        return JSONResponse(
            status_code=e.http_status, content={"error": e.code, "message": e.message}
        )

    try:
        body = json.loads(raw.decode("utf-8")) if raw.strip() else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        _log.info("validate_record outcome=invalid_json")
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_json", "message": "The body is not well-formed JSON."},
        )

    if not isinstance(body, dict):
        _log.info("validate_record outcome=not_object")
        return JSONResponse(
            status_code=422,
            content={
                "error": "not_a_json_object",
                "message": "The body must be a JSON object (a candidate ISAAC record).",
            },
        )

    report = validate_official(body, REPO_ROOT)

    # EXACTNESS — a HARD gate, and the ONE thing on this route that is allowed to turn a
    # schema PASS into an overall refusal. Read this together with the `warnings` note
    # below, because the two are deliberately opposite and the difference is the point.
    #
    # `portal_warnings` is ADVISORY: it may never move `ok`, because doing so would make
    # this module a second authority on *schema validity*. `check_exactness` is not an
    # opinion about the science — it reports that a value passes an anchored schema
    # pattern only because Python's `$` also matches before a trailing newline, and
    # `export_draft` REFUSES such a record. If this route returned an unqualified `ok:
    # true` for a record the exporter will not accept, the standalone validator — the
    # surface an operator points at a candidate file precisely to ask "is this good?" —
    # would be the one place that says yes to something the product says no to.
    #
    # `schema_ok` is preserved ALONGSIDE `ok` and remains exactly `validate_official`'s
    # verdict, so nothing is lost: a caller that wants the pure schema answer still has
    # it, under a name that says what it is. `errors` likewise stays schema-only; the
    # exactness findings are a separate list, because they are not schema errors and
    # merging them would attribute an ISAAC policy to the upstream schema.
    exactness = check_exactness(body, REPO_ROOT)

    # R2 — the advisory tier, which this route did not run.
    #
    # Until now `post_validate_record` called `validate_official` and NOTHING else, while
    # the per-record route (`_warnings_payload`) has always also run `portal_warnings`.
    # So the standalone validator — the surface an operator actually points at a
    # candidate file — was the one place the advisory tier was invisible. A record with
    # `measurement.series: []` came back as an unqualified PASS: schema-valid with zero
    # errors (no `minItems`), no signal of any kind that it holds no measured data.
    #
    # `warnings` is ADVISORY and NON-GATING, and the shape says so: `ok` above is
    # computed from `report` alone and is deliberately NOT combined with the warning
    # count. A warning must never be able to turn a PASS into a FAIL here, because that
    # would make this module a second authority on validity alongside the vendored
    # schema. Same serializer as the per-record route, so the two cannot drift.
    warnings = serialize.warnings_to_dict(portal_warnings(body))
    _log.info(
        "validate_record outcome=ok ok=%s error_count=%d exactness_error_count=%d "
        "warning_count=%d",
        report.ok and exactness.ok,
        len(report.errors),
        len(exactness.errors),
        len(warnings.get("warnings", [])),
    )
    return {
        "ok": report.ok and exactness.ok,
        "schema_ok": report.ok,
        # BOTH verdicts. The web Validator renders `summary` and (today) does NOT
        # render `exactness_errors`, so a schema-only summary would put a FAIL badge
        # above a pane reading "PASS — valid against official ISAAC schema v1.05"
        # with no reason stated anywhere. Shared renderer with `isaac validate
        # --official` so the two surfaces cannot drift.
        "summary": combined_summary(report.render(), exactness),
        "errors": [{"path": e.path, "message": e.message} for e in report.errors],
        "exactness_errors": [
            {"path": e.path, "message": e.message} for e in exactness.errors
        ],
        "schema_version": EXPECTED_VERSION,
        **warnings,
    }


# --- 10. audit ----------------------------------------------------------------


@router.post(
    "/experiments/{experiment_id}/audit",
    tags=[TAG_VALIDATION],
    summary="Audit a Record's Exported Artifacts",
    description=(
        "Runs the deterministic audit over the official record and evidence "
        "sidecar this record's export wrote, returning the per-record "
        "official-schema report, its evidence-coverage counts, and the rendered "
        "text report.\n\n"
        "A record that has not been exported yet returns `200` with no rows and a "
        "message saying so, rather than an error. Read-only."
    ),
    response_description="The audit rows and the rendered text report.",
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def post_audit(scope: TutorialScopeDep, experiment_id: ExperimentId):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    # REVIEW ITEM F5 — `any_unit_exported()`, not `exported()`. This gate asserted
    # something false about a fully-exported fan-out, whose N records were all on
    # disk. Measured on `c467dc7`:
    #
    #     POST .../audit -> {"records": [], "text": "No records found.",
    #                        "message": "Nothing exported yet — export this
    #                                    experiment before auditing."}
    #
    # The audit itself was never fan-out-blind: `audit_records` GLOBS this
    # experiment's own records dir (see the note below) and would have found every
    # run's record. Only the predicate in front of it was.
    #
    # `any_unit_exported()` and not `all_units_exported()`, deliberately: a PARTIALLY
    # exported fan-out has records on disk and they are worth auditing, so the
    # stricter aggregate would have replaced one false "nothing exported" with a
    # narrower one. This route describes WHAT IS ON DISK; the export gate is where the
    # all-or-nothing aggregate belongs (contract §3 D4). For an experiment with no
    # runs the two are the same function of the same field, so the refusal below is
    # byte-identical for an experiment that has no runs — which is how every
    # experiment starts, and how it stays until a run is added through
    # `POST /api/experiments/{experiment_id}/runs`. (This comment used to end "for
    # every experiment this API can create". That was true when written and stopped
    # being true the same day, when #109 added that route. Corrected rather than
    # deleted, because the same sentence had propagated to four other sites and only
    # three were caught on the first pass.)
    if not exp.any_unit_exported():
        return {
            "records": [],
            "text": "No records found.",
            "message": "Nothing exported yet — export this experiment before auditing.",
        }
    # P4 review FIX C — checked, NOT changed. Unlike its sibling read endpoints this
    # one never raised on a missing artifact, and it needs no defensive read: it does
    # not open a path derived from `record_id` at all. `audit_records` GLOBS
    # `records_dir/*.json`, so a deleted artifact simply yields no rows (200, `text:
    # "No records found."`), and a corrupt one is reported as `invalid JSON` against
    # `path.name` — a basename, never a path. Pinned by
    # `test_export_recovery.test_audit_already_tolerates_a_missing_artifact`.
    results = audit_records(exp.records_dir, REPO_ROOT)
    return serialize.audit_to_dict(results, render_audit(results))


# --- 11. warnings (advisory, non-gating) --------------------------------------


def _unit_warnings_entry(unit: ws.ExportUnit) -> dict:
    """One export unit's advisory warnings, ADDRESSED TO ITS RUN.

    Mirrors ``_validate_unit``: ``dry_run`` is per unit and states WHICH document the
    advice describes — the written record when this unit is materialised, an in-memory
    candidate otherwise. An unreadable written record degrades to the candidate and
    SAYS so, because this channel carries no verdict and ``dry_run`` is exactly the
    field that distinguishes the two documents.

    **It does not raise, and that is a DIFFERENCE from the single-record path rather
    than a restatement of it.** ``_warnings_payload`` calls ``export_draft``
    unguarded, so a draft that makes the transform throw takes that route to a 500;
    here one bad run would take down the advice for every other run in the set, which
    is a worse trade at N units than at one. The degradation is the one this channel
    already has for a draft too broken to produce a record at all
    (``result.record or {}`` below and in ``_warnings_payload``): advise on the empty
    record, with ``dry_run: true`` saying no written record was read. That is a
    deliberately weak answer, not a good one — see the comment in ``_warnings_payload``
    for why it is still preferred to reporting zero warnings, which would read as
    "nothing to advise" about a document nobody could build.
    """
    entry = {
        "run_id": unit.run_id,
        "run_label": unit.run_label,
        "record_id": unit.target_id,
    }
    record = _read_artifact_json(unit.record_path()) if unit.materialised() else None
    if record is not None:
        dry_run = False
    else:
        try:
            result = export_draft(unit.draft, REPO_ROOT)
            record = result.record or {}
        except Exception:
            _log.exception("warnings dry-run failed run=%s", unit.run_id)
            record = {}
        dry_run = True
    payload = serialize.warnings_to_dict(portal_warnings(record))
    return {**entry, "warnings": payload["warnings"], "dry_run": dry_run}


def _fan_out_warnings_payload(exp: Experiment) -> dict:
    """:func:`_warnings_payload` for an experiment WITH RUNS.

    REVIEW ITEM F5. ``exp.exported()`` is permanently False for a fan-out, so the
    single-record path below dry-ran ``exp.draft`` — the EXPERIMENT-LEVEL HALF, which
    holds no measurement, no links and no run content at all, and is never exported.
    Measured on ``c467dc7`` for a fully-exported 2-run fan-out::

        GET .../warnings -> dry_run: true, codes ['NO_LINKS','NO_MEASUREMENT_SERIES']
        exported record keys -> [... 'measurement' ...]

    Every record on disk HAS a measurement block. The advice was true of nothing.

    **The top-level ``warnings`` is the DEDUPLICATED UNION over the runs, in first-seen
    order — not the first failing unit's, which is what ``/validate`` does.** The two
    channels differ in a way that justifies differing here: ``/validate`` returns a
    VERDICT, so a caller reading only ``errors`` must be shown a real failure and any
    aggregation risks implying a whole-set claim. This channel returns ADVICE and
    carries no pass/fail field by design, so the union cannot mislead — it can only
    under- or over-report which run to look at, and ``runs[]`` carries that exactly.
    Deduplication is on the whole ``(code, where, message)`` triple, so two runs
    raising the same advice about the same place appear once, while the same code
    about different places stays two pieces of advice.
    """
    entries = [_unit_warnings_entry(unit) for unit in exp.export_units()]
    seen: set[tuple] = set()
    merged: list[dict] = []
    for entry in entries:
        for warning in entry["warnings"]:
            key = (warning["code"], warning["where"], warning["message"])
            if key not in seen:
                seen.add(key)
                merged.append(warning)
    return {
        "advisory": True,
        "gating": False,
        "warnings": merged,
        # Same rule as `/validate`: `dry_run: false` is the strong claim that a
        # WRITTEN record was advised on, so it must not be made for the set while any
        # member's advice came from an in-memory candidate.
        "dry_run": any(entry["dry_run"] for entry in entries),
        "runs": entries,
    }


def _warnings_payload(exp: Experiment) -> dict:
    if exp.runs:
        return _fan_out_warnings_payload(exp)
    # P4 review FIX C — read DEFENSIVELY (see `post_validate`). `getExportReadiness`
    # fetches this in the same `Promise.all` as `/artifacts`, so an unguarded read here
    # took the whole readiness view down with an unhandled 500.
    record = _read_artifact_json(exp.record_path()) if exp.exported() else None
    if record is not None:
        dry_run = False
    else:
        # Advisory check on the dry-run record (populated even when official fails).
        #
        # This is ALSO the degradation when the record is marked exported but its
        # artifact cannot be read — and it is honest here in a way it would not be in
        # `post_validate`, because this channel carries no verdict at all (no pass,
        # fail, validity or exportability field, by design) and it already publishes
        # the one distinction that matters: `dry_run` states WHICH document was
        # checked. `dry_run: true` says "these warnings came from the in-memory export
        # candidate", which is exactly what happened. Zero warnings would instead
        # imply "nothing to advise" about a document nobody read, and warnings
        # computed from `{}` would be advice about a record that does not exist.
        result = export_draft(exp.draft, REPO_ROOT)
        record = result.record or {}
        dry_run = True
    payload = serialize.warnings_to_dict(portal_warnings(record))
    payload["dry_run"] = dry_run
    return payload


#: Both the GET and the POST form call ``_warnings_payload`` and nothing else, so
#: they are documented with the same consumer-facing text.
_WARNINGS_DESCRIPTION = (
    "Advisory, non-gating warnings for this record. For an already-exported "
    "record the written record is checked (`dry_run: false`); otherwise — "
    "including when that written record cannot be read — the in-memory export "
    "candidate is checked (`dry_run: true`). Always read `dry_run` to know which "
    "document the advice describes.\n\n"
    "This channel deliberately carries no pass, fail, or validity field, and it "
    "never blocks an export — read it as advice for a human, alongside the "
    "official-schema verdict, not instead of it. The `GET` and `POST` forms are "
    "equivalent: both are read-only and return the same payload.\n\n"
    "A record with **runs** exports one official record per run, so it is advised "
    "on per run: `runs[]` carries each run's own warnings and its own `dry_run`. "
    "The top-level `warnings` is the deduplicated union over the runs — advice, "
    "unlike a verdict, is safe to aggregate — and the top-level `dry_run` is "
    "`true` if any run's advice came from an in-memory candidate rather than a "
    "written record."
)
_WARNINGS_RESPONSE_DESCRIPTION = (
    "The advisory warnings and whether they were computed from a dry run. No "
    "verdict field is present, by design."
)


@router.get(
    "/experiments/{experiment_id}/warnings",
    tags=[TAG_VALIDATION],
    summary="Get a Record's Advisory Warnings",
    description=_WARNINGS_DESCRIPTION,
    response_description=_WARNINGS_RESPONSE_DESCRIPTION,
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def get_warnings(scope: TutorialScopeDep, experiment_id: ExperimentId):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    return _warnings_payload(exp)


@router.post(
    "/experiments/{experiment_id}/warnings",
    tags=[TAG_VALIDATION],
    summary="Re-Check a Record's Advisory Warnings",
    description=_WARNINGS_DESCRIPTION,
    response_description=_WARNINGS_RESPONSE_DESCRIPTION,
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def post_warnings(scope: TutorialScopeDep, experiment_id: ExperimentId):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    return _warnings_payload(exp)


# --- 12. evidence -------------------------------------------------------------


@router.get(
    "/experiments/{experiment_id}/evidence",
    tags=[TAG_EVIDENCE],
    summary="Get a Record's Evidence Trail",
    description=(
        "The field-by-field evidence trail for this record: each official path, "
        "its value, the kind of support behind it, and the source file and locator "
        "cited.\n\n"
        "For an already-exported record the trail is read from the evidence "
        "sidecar written alongside the official record; otherwise — including when "
        "that sidecar or record cannot be read — it is read from the draft's own "
        "evidence envelopes, which are the sidecar's own source. Read-only.\n\n"
        "TWO KINDS OF ENTRY, AND ONLY THE FIRST CARRIES A VALUE. A dotted official "
        "path, an `assets:` key and an `implicit:` key resolve their value. A "
        "BLOCK-LEVEL entry — a `qc:`, `series:`, `descriptors:`, `attribution:` or "
        "`links:` key — carries its support with `value: null`, exactly as the "
        "exported sidecar's own trail does, so the same record reads the same way "
        "before and after export. Those entries were MISSING from the draft trail "
        "until 2026-08-25: a record created through this API and completed to "
        "`ready_to_export` served an empty trail, because its confirmations live in "
        "blocks the draft reader did not walk.\n\n"
        "**FIVE BLOCK NAMESPACES, NOT THREE, AND THEY ARE NOT ALL CONFIRMATIONS.** "
        "This paragraph named `qc:`, `series:` and `descriptors:` and called them "
        "*\"recorded when a scientist confirms a verdict, a spectrum or a "
        "descriptor\"*. Measured across the five seeded worked examples, the trail "
        "also carries `attribution:<name>|<role>` — two entries per record, the "
        "largest single namespace this reader added — and those are SPREADSHEET "
        "CITATIONS extracted from a source document, not confirmations anybody "
        "gave. `links:<rel>|<target>|<basis>` is the fifth; no fixture in this "
        "repository produces one, and it is named here rather than discovered "
        "later. `assets:` and `implicit:` come from a different reader and DO "
        "resolve a value, as the paragraph above says."
    ),
    response_description=(
        "One evidence entry per field carrying a value, plus one per block-level "
        "confirmation (those carry `value: null`)."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def get_evidence(scope: TutorialScopeDep, experiment_id: ExperimentId):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    # P4 review FIX C — read DEFENSIVELY (see `post_validate`). `getEvidenceBundle`
    # fetches this in the same `Promise.all` as `/artifacts`, so an unguarded read here
    # took the whole evidence explorer down with an unhandled 500.
    record = _read_artifact_json(exp.record_path()) if exp.exported() else None
    sidecar = _read_artifact_json(exp.sidecar_path()) if exp.exported() else None
    if record is not None and sidecar is not None:
        entries = serialize.evidence_trail_from_sidecar(sidecar, record)
    else:
        # DEGRADE TO THE DRAFT TRAIL, which is what a not-yet-exported record returns
        # and is not a substitute source in any meaningful sense: the sidecar is a
        # projection of these very envelopes, written at export time. So the trail is
        # still this record's own evidence, from its origin, never fabricated — and
        # `evidence_trail_from_sidecar` needs BOTH files anyway (it reads values from
        # the record and support from the sidecar), so one absent file is already
        # enough to make the sidecar trail unbuildable.
        #
        # Deliberately NO new response field, and the reason given here USED TO BE
        # FALSE FOR A FAN-OUT (review item F-G). It said the one honest thing a marker
        # would add is "already published by `/artifacts` as `artifact.state:
        # "stale"`". Measured on `74509c4` for a fully-exported 2-run fan-out:
        # `/artifacts` reports `state: "current"`, never `stale`, so the named
        # compensating signal did not exist on the path that most needs it.
        #
        # The two branches are not one case, and the old sentence collapsed them:
        #
        #   * PAIR PRESENT BUT UNREADABLE (a zero-run experiment marked exported whose
        #     files will not parse) — `/artifacts` DOES force `stale` here, a few lines
        #     above, precisely so the block never implies a pair that is not on disk.
        #     That half of the old claim holds, and it is the half a marker would
        #     duplicate.
        #   * NO PAIR AT ALL (a fan-out: `exported()` is permanently False, so the two
        #     reads never happen). `/artifacts` answers `current` with four nulls and
        #     `reason: FAN_OUT_ARTIFACT_REASON`, which is correct about the
        #     EXPERIMENT'S OWN pair. What no surface says is that THIS endpoint then
        #     served a different document — the experiment-level draft trail, omitting
        #     every run-level field.
        #
        # It is still not fixed by a marker, because a marker is not what is missing:
        # the fan-out answer needs a `runs[]` array, N sidecar reads and a frontend
        # that can display more than one trail (`api.ts::getEvidence` discards every
        # key except `evidence`). That is the Run-workspace slice. See the STATED, NOT
        # FIXED entry for `get_evidence` in `workspace.py`, which now records this as
        # deferred for cost rather than blocked on a product question. The description
        # above states the fallback; this comment states what the description cannot,
        # which is which of the two branches a reader is in.
        if exp.exported():
            _log.warning(
                "evidence: record %s is marked exported but its artifact pair could "
                "not be read; serving the draft evidence trail instead",
                exp.id,
            )
        # TWO READERS, AND THE SECOND ONE IS WHY A COMPLETED RECORD'S TRAIL IS NO LONGER
        # EMPTY. `evidence_trail_from_draft` walks `fields`, `implicit` and `assets`;
        # `complete.apply_answers` writes the confirmations for `series`, `qc` and the
        # descriptor block into `block_evidence` and `descriptors_outputs`. Measured
        # before this line existed: a record created through `POST /api/experiments`,
        # every question answered, `official.ok: true`, `ready_to_export` — and this
        # endpoint served `{"evidence": []}`, while `isaac_inspect_evidence`'s
        # description promised "each official path, its value, the kind of support behind
        # it, and the source file and locator cited". The five seeds hid it: their
        # `fields` map comes from a fixture sheet, so they returned 28-36 entries, and a
        # created record's `fields` map is empty.
        #
        # COMPOSED HERE RATHER THAN INSIDE THE WALKER, deliberately — see
        # `serialize.confirmed_block_trail_from_draft` for the two consumers that
        # widening the walker would have made WRONG (`provenance._DESCRIBED_DRAFT_KEYS`'
        # own disclosure, and `conflict_resolution`, which would have read an append-only
        # confirmation list as two competing answers).
        #
        # IT DOES NOT CLOSE THE FAN-OUT GAP the long comment above states, and it must not
        # be read as doing so: these are the RECORD's own confirmed blocks. On a fan-out
        # the run-level blocks live on the runs, this endpoint still serves the
        # experiment-level draft only, and that remains STATED, NOT FIXED.
        entries = serialize.evidence_trail_from_draft(exp.draft) + (
            serialize.confirmed_block_trail_from_draft(exp.draft)
        )
    return {"evidence": entries}


# --- 12b. evidence classification (P28.5, evidence-support axis, read-only) ----

#: The six evidence-support classes, in the display precedence used everywhere.
#: The single source for the ``counts`` histogram key set. ``unreadable`` is a
#: bucket of its own — see ``runtime_records.EVIDENCE_CLASSES`` for why it is not
#: folded into ``unknown``.
_EVIDENCE_CLASSES = (
    "supported",
    "inferred_candidate",
    "insufficient_evidence",
    "conflicting_evidence",
    "unknown",
    "unreadable",
)


@router.get(
    "/experiments/{experiment_id}/evidence-classification",
    tags=[TAG_EVIDENCE],
    summary="Classify a Record's Evidence Support",
    description=(
        "Per-field evidence-support classification for this record's current "
        "state, plus a histogram over the six classes — `supported`, "
        "`inferred_candidate`, `insufficient_evidence`, `conflicting_evidence`, "
        "`unknown` and `unreadable` — bound to the authoritative `record_rev` so a "
        "client can tell when its view is stale.\n\n"
        "`unreadable` means this entry's stored evidence could not be read, so its "
        "evidence support is unknown to the server. It is deliberately NOT "
        "`unknown`, which asserts that nothing defensible is recorded.\n\n"
        "This carries the evidence-support axis only. It deliberately reports no "
        "validity, completion, exportability, or advisory verdict; those live in "
        "their own operations. Read-only, and it takes no lock."
    ),
    response_description=(
        "The per-field classifications, the six-class histogram, and the "
        "revision they describe."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def get_evidence_classification(
    scope: TutorialScopeDep, experiment_id: ExperimentId, response: Response
):
    """Typed evidence-support classification for the CURRENT record (P28.4 view).

    Read-only; carries ONLY the evidence-support axis — ``field_results`` (from the
    frozen ``evidence_classify.classify_fields``) plus a same-axis ``counts``
    histogram — bound to the authoritative ``record_rev`` so a client can detect a
    stale view. It deliberately carries NO validity/completion/advisory verdict
    (no ``valid``/``ok``/``exportable``/``complete``/``blocking``/``warnings``);
    those stay in their own endpoints. No lock is taken (pure read).
    """
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    field_results = evidence_classify.classify_fields(exp.draft)
    counts = {c: 0 for c in _EVIDENCE_CLASSES}
    for fr in field_results:
        counts[fr["classification"]] += 1
    response.headers["ETag"] = exp.etag()
    return {"record_rev": exp.rev, "field_results": field_results, "counts": counts}


# --- 12c. unified provenance (two dimensions, read-only) ----------------------


def _record_resolution_states(exp: Experiment) -> dict[str, str]:
    """``address -> resolution state`` for the RECORD's own draft.

    Scoped here rather than inside ``conflict_resolution``, which requires its
    caller to pre-filter: a record-level decision carries ``run_id is None``, and
    letting that module infer the scope would put the scope rule in two places.
    """
    readable, _unreadable = cr.resolutions_from_draft(exp.draft)
    return cr.resolution_states(
        exp.draft, [entry for entry in readable if entry.run_id is None]
    )


def _run_resolution_states(exp: Experiment, run_obj) -> dict[str, str]:
    """``address -> resolution state`` for ONE run's own draft.

    The decisions are read from the RECORD's draft whatever the subject is, because
    one record-level list holds run-scoped rows too — see
    ``conflict_resolution``'s module docstring for why the storage is not per-run.
    """
    readable, _unreadable = cr.resolutions_from_draft(exp.draft)
    return cr.resolution_states(
        run_obj.draft, [entry for entry in readable if entry.run_id == run_obj.id]
    )




@router.get(
    "/experiments/{experiment_id}/provenance",
    tags=[TAG_EVIDENCE],
    summary="Describe Where a Record's Values Came From",
    description=(
        "Two SEPARATE answers for each address on this record: `origins` — where "
        "the value came from — and `review_state` — what, if anything, "
        "establishes it. They are independent dimensions and are never combined "
        "into one word: where a value came from says nothing about whether it is "
        "backed, so a value read out of a file, produced by a derivation rule, or "
        "inherited can perfectly well still be awaiting review.\n\n"
        "`origins` is a SET, because one address can legitimately carry several "
        "citations of different kinds. `primary_origin` picks one of them by a "
        "fixed documented order, never by whichever citation happens to be stored "
        "first, and that order announces a mixed-origin value under the origin a "
        "reader most needs to know about rather than its most reassuring one. "
        "When nothing stored says where a value came from, the origin is "
        "`unknown` — a statement about the record, never a plausible default.\n\n"
        "`review_state` is `conflict` when the record's own evidence asserts "
        "incompatible values, `unmapped` for captured content that has no schema "
        "home and no review yet, `supported` only when the stored status is "
        "`verified` AND at least one readable citation backs it, and "
        "`needs_review` for everything else — including anything this server "
        "cannot positively place. It is not a validity, completion or export "
        "verdict, and it decides nothing about whether this record can be "
        "exported.\n\n"
        "Pass `run` to describe one run instead of the record: each address then "
        "says whether the run holds the value itself or resolves to the "
        "record-level value it inherits. Nothing here is stored — every answer is "
        "derived on read from content the record already carries. Read-only."
    ),
    response_description=(
        "One entry per described address, plus what was deliberately not "
        "described: how many notes exist against how many are listed, and the "
        "record-level blocks that carry no value envelope to describe."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_RUN_NOT_FOUND},
)
def get_provenance(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    run: Annotated[
        str | None,
        Query(
            description=(
                "Describe this run of the record rather than the record itself. "
                "Omit it for the record. An id this record has no run for is "
                "refused rather than answered from the record."
            )
        ),
    ] = None,
):
    """The two provenance dimensions for one record, or for one of its runs.

    Read-only and lock-free. Both dimensions are DERIVED on every call from
    content that is already stored — no new field is written, and nothing about
    the truth path, official validation, or export is consulted or changed.

    A run is addressed by a QUERY parameter rather than its own path segment
    because the answer is the same document either way: the record's own draft is
    the default subject, and `run` narrows the subject to one of its runs. An
    unknown run id is a `404` naming the run (the record itself was found), never
    a silent fallback to the record-level answer.
    """
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)

    if run is None:
        # Narrowed to notes that are ABOUT THE RECORD, symmetrically with the run
        # branch below. This used to pass every note, including ones captured
        # against a specific run — and `_note_refs_by_path` keys purely on
        # `mapped_field_path`, never on `run_id`. So a note captured against run 2
        # and mapped to a field path the record also carries appeared in the
        # RECORD's `note_refs` with no run marker, and was counted in
        # `notes_summary` as an unmapped entry of the record. A reader had no way
        # to tell it was about a different run's value.
        #
        # That is the exact invention the run branch is careful to refuse,
        # committed in the opposite direction. One rule, both ways: a note is
        # described by the subject it was captured against, and by nothing else.
        record_notes = [n for n in exp.sorted_notes() if n.run_id is None]
        body = provenance.describe_experiment(
            exp.draft, record_notes, _record_resolution_states(exp)
        )
    else:
        run_obj = exp.get_run(run)
        if run_obj is None:
            return _run_not_found(experiment_id, run)
        # Notes are narrowed to the ones captured against THIS run. A note with no
        # run is a note about the record as a whole; attaching it to whichever run
        # is being viewed would be exactly the invention `notes` refuses when it
        # keeps `run_id` absent rather than guessing one.
        run_notes = [n for n in exp.sorted_notes() if n.run_id == run]
        # THE RECORD'S STATES UNDER THE RUN'S OWN. An inherited address is decided
        # once, at the record, so its state has to reach a run's view — and a run's
        # own decision about its own address must win over a record-level one that
        # happens to share the address name. `provenance` does no scope reasoning at
        # all, deliberately, so the merge is stated here.
        body = provenance.describe_run(
            run_obj.draft,
            exp.resolve_run(run_obj),
            run_notes,
            {
                **_record_resolution_states(exp),
                **_run_resolution_states(exp, run_obj),
            },
        )

    response.headers["ETag"] = exp.etag()
    return {
        "experiment_id": exp.id,
        "run_id": run,
        "record_rev": exp.rev,
        **body,
    }


# --- 12d. conflict resolution (read the disagreement, record ONE human decision) --
#
# WHAT THESE TWO OPERATIONS ARE FOR. `evidence_classify` flags an address the
# moment two distinct non-null answers are recorded against it, and NOTHING in this
# application removes an evidence entry — `POST .../answers` and `POST .../edit`
# each APPEND a `user_confirmation`. So a scientist who answers a question, notices
# a typo and answers it again has manufactured a finding that no surface this build
# offered could clear. `GET .../conflicts` is where they can finally SEE the
# competing answers, and `POST .../conflicts/resolve` is where they can say which
# one they stand behind.
#
# WHAT THEY ARE NOT. The resolve operation writes NO scientific value. It records
# WHICH of the already-recorded answers a person chose; making that the field's
# value would be a SECOND path by which scientific content changes, and this
# application deliberately has exactly one (a confirmed answer or edit, recorded as
# `user_confirmation` evidence). `conflict_resolution.ConflictResolution` cannot
# even represent an applied value — `is_field_value` and `is_evidence` are
# read-only constants on a frozen, slotted dataclass, and both are serialised on
# the wire so the guarantee survives the boundary.
#
# NOTHING IS EVER REMOVED HERE EITHER, in either direction. The competing evidence
# is untouched by a resolution — the decision is written BESIDE it, under the
# draft's own top-level key — so a resolved address keeps every citation it had and
# is still reported by this surface. `resolution_state` is what a reader branches
# on, never the absence of a row.
#
# TWO SCOPES, AND THE GAP THAT MADE THE SECOND ONE NECESSARY.
# `GET .../evidence-classification` classifies the RECORD's own draft only, so a
# conflict living in a run's own fields was invisible outside submit time. `run`
# narrows the subject to that run's OWN draft. It is deliberately not the run's
# RESOLVED draft: an inherited address's evidence lives at the record and is
# reported there, and describing it under both scopes would offer a scientist two
# places to decide one disagreement, producing two resolutions with different
# `run_id`s for a single conflict.
#
# ONE VALIDATOR, THE RECORD'S. A resolution is stored inside the experiment's own
# state document — one record-level list, run-scoped rows distinguished by their
# `run_id` — so writing one REWRITES THE RECORD and takes the RECORD's `If-Match`
# even when it is about a run. That is the rule the note operations already follow,
# for the reason `patch_run`'s description records: a second concurrency scheme
# with no consumer is a trap.


#: The body keys the resolve operation accepts. Anything else is REFUSED rather
#: than ignored, exactly as the note operations refuse an unknown key and for the
#: same reason: a caller that sends `{"applied": true}` or `{"verified": true}`
#: alongside its decision must be told the key means nothing here, not answered
#: 200 while it is silently dropped. A resolution records a choice; it applies
#: nothing and verifies nothing, so a key naming either is refused.
_CONFLICT_RESOLVE_KEYS = frozenset(
    {
        "address",
        "run_id",
        "outcome",
        "chosen_value",
        "chosen_from",
        "rationale",
        "confirmed_by_user",
    }
)


def _conflict_refusal(error: str, message: str, **extra) -> JSONResponse:
    """One typed 422. Every refusal on these two operations is one of these.

    THE SAME SHAPE AS ``_note_refusal`` AND DELIBERATELY NOT THE SAME FUNCTION.
    That helper's docstring claims every refusal on the NOTE routes is one of its
    responses, and a shared helper would make the claim unverifiable for either
    feature. The shape is the module's convention; the name says which contract the
    body belongs to.
    """
    return JSONResponse(
        status_code=422, content={"error": error, "message": message, **extra}
    )


def _unknown_conflict_keys(body: dict) -> JSONResponse | None:
    """Refuse a body key the resolve operation does not accept."""
    refused = sorted(str(key) for key in body if key not in _CONFLICT_RESOLVE_KEYS)
    if not refused:
        return None
    return _conflict_refusal(
        "unrecognized_field",
        (
            "These keys are not part of this request. Nothing was written. A "
            "resolution records which of the competing answers a person chose; it "
            "writes no field value, mints no evidence and verifies nothing, so a "
            "key naming one of those is refused rather than accepted and ignored."
        ),
        key=refused[0],
        keys=refused,
    )


def _conflict_subject(exp: Experiment, run: str | None):
    """``(draft, None)`` for the described subject, or ``(None, <404 response>)``.

    A RUN IS DESCRIBED BY ITS OWN DRAFT. See the section comment for why the
    resolved draft is deliberately not used: an inherited address is decided once,
    at the record, and offering it under a run's scope as well would let one
    disagreement collect two decisions.
    """
    if run is None:
        return exp.draft, None
    run_obj = exp.get_run(run)
    if run_obj is None:
        return None, _run_not_found(exp.id, run)
    return run_obj.draft, None


def _conflict_payload(exp: Experiment, draft: dict, run: str | None) -> dict:
    """The conflict surface for one subject, plus what it could not read.

    The resolutions are read from ``exp.draft`` whatever the subject is, because one
    record-level list holds run-scoped decisions too — see
    ``conflict_resolution``'s module docstring for why the storage is not per-run.
    """
    readable, unreadable = cr.resolutions_from_draft(exp.draft)
    # The live run ids, so a decision whose run has been REMOVED is still reported at
    # record scope rather than being reachable from nowhere. `remove_run` leaves the
    # decision row in the draft on purpose (nothing here deletes one), and the run
    # scope answers 404 for a run the record no longer has, so without this the row is
    # invisible while sitting in the document. See `conflict_report`'s `live_run_ids`
    # note for why it is flagged rather than folded in with the ordinary orphans.
    report = cr.conflict_report(
        draft,
        resolutions=readable,
        run_id=run,
        live_run_ids=frozenset(r.id for r in exp.sorted_runs()),
    )
    return {
        "experiment_id": exp.id,
        "run_id": run,
        "record_rev": exp.rev,
        **report,
        # A DISCLOSURE OF WHAT THIS BUILD COULD NOT PRESENT AS A DECISION, counted
        # rather than rendered, for the reason the notes list counts its own: this
        # server can neither say what a refused entry contains without inventing it
        # nor drop it, so the entry is preserved in the record verbatim and the
        # count of them travels beside what could be read. Reporting nothing here
        # when there are some would be the silent discard the whole feature refuses.
        "unreadable_resolution_entries": len(unreadable),
        # THE SERVER'S OWN VOCABULARIES, for the reason the notes list serves its
        # `sources`: the alternative is transcribing three closed sets into a client
        # bundle, where they are free to drift from the sets this route enforces.
        "outcomes": list(cr.RESOLUTION_OUTCOMES),
        "chosen_from_values": list(cr.CHOSEN_FROM_VALUES),
        "states": list(cr.RESOLUTION_STATES),
        "experiment_version": exp.version_token(),
    }


_R_CONFLICT_RUN = {
    404: {
        "description": (
            "No experiment in the selected workspace has that id, that experiment "
            "has no run with the id given in `run`, or the "
            "`X-Isaac-Tutorial-Session` header named a worked-example session that "
            "does not exist. A run is never answered from the record instead."
        )
    },
}


@router.get(
    "/experiments/{experiment_id}/conflicts",
    tags=[TAG_EVIDENCE],
    summary="List a Record's Evidence Conflicts",
    description=(
        "Every address on this record whose own evidence asserts more than one "
        "distinct value, with the competing answers themselves, the citations "
        "behind each one, a deterministic explanation of why they are treated as a "
        "disagreement, and whichever decision a person has already recorded about "
        "it. Read-only, and it takes no lock.\n\n"
        "THIS OPERATION RETURNS THE COMPETING VALUES, and the conflict disclosure "
        "stored on a submission deliberately returns addresses only. The two are "
        "not an inconsistency to be tidied up in either direction: that disclosure "
        "exists for navigation — which addresses carried conflicts when the record "
        "was submitted — and the values live in the revision snapshot beside it, so "
        "copying them in would give one value two homes. This is the surface a "
        "person decides on, and a scientist cannot choose between answers they are "
        "not shown.\n\n"
        "A conflict is always WITHIN one address's own evidence list. It is not a "
        "disagreement between two fields, and it is not a disagreement about where "
        "a value came from: two citations asserting the same value are not in "
        "conflict however different their sources, so the answers are grouped by "
        "value and each group carries the citations that assert it.\n\n"
        "AN ALREADY-DECIDED ADDRESS IS STILL LISTED. Nothing in this API removes an "
        "evidence entry, so the competing citations remain stored forever and the "
        "address goes on classifying as conflicting; hiding it would hide the "
        "decision along with the disagreement. Read `resolution_state`, which is "
        "`absent` when nobody has decided, `current` for a decision that still "
        "covers exactly these answers, `stale` for one made over a different set "
        "because further competing evidence has arrived since, and `deferred` when "
        "a person looked and declined to decide. Only `current` clears a conflict, "
        "and a superseded decision is still returned in full rather than deleted.\n\n"
        "Pass `run` to describe one run's OWN fields instead of the record's. An "
        "address a run inherits is decided once, at the record, so it is described "
        "there and not under each run — otherwise one disagreement could collect "
        "two decisions. `resolutions_without_conflict` reports the other direction: "
        "a stored decision whose address this subject carries no conflict at, "
        "reported rather than silently omitted. `unreadable_resolution_entries` "
        "counts stored decisions this build could not read; they are preserved in "
        "the record untouched and counted rather than rendered, because saying what "
        "one contains would mean inventing it."
    ),
    response_description=(
        "One entry per conflicting address with its competing answers, the "
        "per-state counts, the closed vocabularies a decision must use, and the "
        "record's current `ETag`."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_CONFLICT_RUN},
)
def get_conflicts(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    run: Annotated[
        str | None,
        Query(
            description=(
                "Describe this run's own fields rather than the record's. Omit it "
                "for the record. An id this record has no run for is refused "
                "rather than answered from the record."
            )
        ),
    ] = None,
):
    """The resolution surface: what is in conflict, and what was decided about it.

    Read-only and lock-free. Everything is DERIVED on read from content the record
    already carries — the conflict rule from ``evidence_classify``, the staleness
    comparison from ``conflict_resolution.state_of`` — so no state is written and
    nothing about official validation or export is consulted.
    """
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    draft, missing = _conflict_subject(exp, run)
    if missing is not None:
        return missing
    response.headers["ETag"] = exp.etag()
    return _conflict_payload(exp, draft, run)


@router.post(
    "/experiments/{experiment_id}/conflicts/resolve",
    tags=[TAG_EVIDENCE],
    summary="Record a Decision About an Evidence Conflict",
    description=(
        "Records which of an address's competing answers a scientist stands "
        "behind — or that they looked and declined to decide — and returns the "
        "decision with its full history.\n\n"
        "IT DOES NOT CHANGE THE FIELD'S VALUE, and that is a design decision rather "
        "than an omission. Recording which recorded answer a person chose and "
        "writing that answer into the field are two different acts, and the second "
        "already has exactly one path in this application: an answer or a "
        "correction sent with `confirmed_by_user: true`, stored as user-confirmation "
        "evidence. Wiring a decision into that path would create a second way for "
        "scientific content to change, which is a decision for its own slice. The "
        "stored decision reports `is_field_value: false` and `is_evidence: false` "
        "on the wire for the same reason.\n\n"
        "NOTHING PICKS A WINNER FOR YOU. `chosen_value` arrives only from a request "
        "that carried `confirmed_by_user: true`; an outcome of `resolved` with no "
        "chosen value is refused, so \"the system decided\" is not a state this API "
        "can be made to store. NOTHING IS REMOVED EITHER: the competing citations "
        "are untouched, the address goes on being reported as conflicting, and what "
        "changes is that `resolution_state` becomes `current`.\n\n"
        "`outcome` is `resolved` or `deferred`. `deferred` is a first-class "
        "outcome — a person may legitimately decline to decide — and it does NOT "
        "clear the conflict; it carries no chosen value and no `chosen_from`, "
        "because \"nobody chose\" and \"somebody chose and we filed it as undecided\" "
        "are different facts. For `resolved`, `chosen_from` says whether the value "
        "is one of the recorded answers (`candidate`) or a new one the scientist "
        "typed because all of them were wrong (`edited`); the two are different "
        "claims, and a value that was never asserted cannot be labelled "
        "`candidate`.\n\n"
        "Requires `confirmed_by_user: true` and the RECORD's current `ETag` in "
        "`If-Match` — omitted is `428`, malformed is `400`, and stale is `412` with "
        "nothing written. The record's validator is the right one even for a "
        "run-scoped decision, because a decision is stored inside the record's own "
        "document; there is deliberately no separate validator for a decision. "
        "Every part of the body is resolved BEFORE the precondition is checked, so "
        "a malformed request is refused whether or not the caller's `ETag` happens "
        "to be current, and a refused request leaves no partial act behind.\n\n"
        "REVISING AN EARLIER DECISION IS ALLOWED and never overwrites it silently: "
        "the act is appended to the decision's history together with the value it "
        "superseded and the set of answers that value was chosen from. "
        "Re-submitting an identical decision OVER THE SAME COMPETING SET is a no-op "
        "— no history entry, and the record's revision does not move. If new evidence "
        "has arrived since, the same body is a RE-AFFIRMATION rather than a no-op: it "
        "is recorded, carrying the digest of the set the earlier value was chosen "
        "from, because standing behind a value again after the disagreement changed is "
        "a different act from standing behind it the first time.\n\n"
        "An address this subject does not carry, an address that is not currently "
        "in conflict, a `chosen_from` of `candidate` whose value is none of the "
        "competing answers, a missing confirmation, a `resolved` outcome with no "
        "value, an unknown run, and a wrong-typed body are each refused with `422` "
        "naming what was wrong. Nothing is written in any of those cases."
    ),
    response_description=(
        "The recorded decision, its derived state against the current competing "
        "answers, and the record's new `ETag`."
    ),
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_TUTORIAL_SCOPE,
        **_R_PRECONDITION,
    },
)
def post_conflict_resolution(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    body: dict = Body(
        ...,
        description=(
            "`{\"confirmed_by_user\": true, \"address\": \"<an address this "
            "operation reported as conflicting>\", \"outcome\": "
            "\"resolved|deferred\", \"chosen_value\": \"<required for resolved>\", "
            "\"chosen_from\": \"candidate|edited\", \"run_id\": \"<optional>\", "
            "\"rationale\": \"<optional>\"}`. Any other key is refused with `422`."
        ),
    ),
    if_match: str | None = Header(
        default=None,
        alias="If-Match",
        description=(
            "Required. The RECORD's current `ETag`, exactly as a read operation "
            "returned it — a decision is stored inside the record's own document, "
            "so a run-scoped one takes this validator too."
        ),
    ),
):
    """Record one human decision about one conflicting address.

    THE CHOSEN VALUE DOES NOT BECOME THE FIELD'S VALUE, deliberately. See the
    operation description: this application has exactly one path by which
    scientific content changes, and adding a second one is a decision for a later
    slice rather than an assumption for this one.

    THE RECORD's ``If-Match``, even for a run-scoped decision, because a decision
    lives in one record-level list inside the experiment's own state document
    (``conflict_resolution.DRAFT_KEY``) — the arrangement, and the reason, that the
    note operations already follow.

    EVERY INPUT IS RESOLVED BEFORE THE PRECONDITION IS EVEN CHECKED, so a refused
    request can never leave a partial act behind and a malformed body is a 422
    whether or not the caller's validator happens to be current. The model's own
    refusals are caught and returned as a typed 422 rather than escaping as a 500 —
    ``complete.py`` once answered a wrong-typed structured value with a traceback
    out of the truth core, and that is the shape this catch exists to refuse.
    """
    # Existence pre-check OUTSIDE the lock, exactly as every other mutation does it,
    # so a bogus id never pins a permanent entry in the never-evicting lock map.
    if ws.load_experiment(experiment_id, session_id=scope) is None:
        return _not_found(experiment_id)
    with ws.record_lock(experiment_id, session_id=scope):
        exp = ws.load_experiment(experiment_id, session_id=scope)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock window
        if not isinstance(body, dict):
            return _conflict_refusal(
                "invalid_body", "The request body must be a JSON object."
            )
        refused = _unknown_conflict_keys(body)
        if refused is not None:
            return refused
        outcome = body.get("outcome")
        if outcome not in cr.RESOLUTION_OUTCOMES:
            return _conflict_refusal(
                "unknown_resolution_outcome",
                (
                    "`outcome` must be `resolved` — a person decided which of the "
                    "competing answers is right — or `deferred` — a person looked "
                    "and declined to decide, which is a recorded outcome and does "
                    "not clear the conflict. There is no default: nothing here "
                    "decides on a scientist's behalf."
                ),
                outcome=outcome if isinstance(outcome, str) else None,
                allowed=list(cr.RESOLUTION_OUTCOMES),
            )
        if body.get("confirmed_by_user") is not True:
            return _confirmation_required("record a decision about a conflict")

        run_id = body.get("run_id")
        if run_id is not None:
            # A DECISION MAY NOT NAME A RUN THIS RECORD DOES NOT HAVE. A `422` and
            # not a `404`, exactly as it is when capturing a note: the record was
            # found, and what is wrong is one field of the body.
            if not isinstance(run_id, str) or exp.get_run(run_id) is None:
                return _conflict_refusal(
                    "unknown_run",
                    (
                        "This record has no run with that id, so a decision cannot "
                        "be recorded against it. Omit `run_id` to decide an address "
                        "of the record itself — it is never inferred from the only "
                        "run that happens to exist."
                    ),
                    run_id=run_id if isinstance(run_id, str) else None,
                )
        subject = exp.draft if run_id is None else exp.get_run(run_id).draft

        address = body.get("address")
        if not isinstance(address, str) or not address.strip():
            return _conflict_refusal(
                "invalid_address",
                (
                    "`address` must be the non-blank address of an entry this "
                    "record describes, exactly as the conflict list reports it. "
                    "Nothing was written."
                ),
            )
        trail = {
            str(entry.get("path")): entry
            for entry in serialize.evidence_trail_from_draft(subject)
        }
        entry = trail.get(address)
        if entry is None:
            return _conflict_refusal(
                "unknown_address",
                (
                    "This subject describes no entry at that address, so there is "
                    "no disagreement there to decide. Addresses are reported by the "
                    "conflict list; a run's own addresses and the record's are "
                    "different sets, so check that `run_id` names the subject you "
                    "mean. Nothing was written."
                ),
                address=address,
            )
        classified = {
            result["field"]: result
            for result in evidence_classify.classify_fields(subject)
        }
        classification = (classified.get(address) or {}).get("classification")
        if classification != cr.CONFLICT_CLASSIFICATION:
            return _conflict_refusal(
                "address_not_conflicting",
                (
                    "This address is not currently in conflict — its evidence does "
                    "not assert two different values — so there is nothing here for "
                    "a decision to be about, and recording one would assert that a "
                    "disagreement existed. Nothing was written."
                ),
                address=address,
                classification=classification if isinstance(classification, str) else None,
            )
        competing = cr.competing_from_evidence(entry.get("evidence"))

        chosen_value = body.get("chosen_value")
        chosen_from = body.get("chosen_from")
        rationale = body.get("rationale")
        if rationale is not None and (
            not isinstance(rationale, str) or not rationale.strip()
        ):
            return _conflict_refusal(
                "invalid_rationale",
                (
                    "`rationale` must be a non-blank string when it is supplied. "
                    "Absent is a meaning here — omit it rather than sending an "
                    "empty string, which would be stored as though somebody had "
                    "written a reason. Nothing was written."
                ),
            )
        if rationale is not None and not _is_storable_value(
            rationale, max_bytes=_MAX_NOTE_BYTES
        ):
            return _conflict_refusal(
                "unrepresentable_value",
                (
                    "This rationale could not be stored intact — either it is "
                    "larger than one may be, or it contains characters JSON cannot "
                    "represent — so a record containing it could not be read back. "
                    "It is REFUSED rather than shortened. Nothing was written."
                ),
            )

        if outcome == cr.OUTCOME_RESOLVED:
            if chosen_value is None:
                return _conflict_refusal(
                    "resolution_requires_chosen_value",
                    (
                        "A resolved conflict must record the value the scientist "
                        "chose. Nothing here picks one, so a resolved outcome with "
                        "no value would claim a decision nobody made. Send "
                        "`outcome: \"deferred\"` to record that the conflict was "
                        "looked at and left undecided. Nothing was written."
                    ),
                )
            if chosen_from not in cr.CHOSEN_FROM_VALUES:
                return _conflict_refusal(
                    "unknown_chosen_from",
                    (
                        "`chosen_from` must be `candidate` — the value is one of "
                        "the answers already recorded against this address — or "
                        "`edited` — every recorded answer was wrong and this is a "
                        "new value the scientist typed. They are different claims "
                        "and neither is a default."
                    ),
                    chosen_from=chosen_from if isinstance(chosen_from, str) else None,
                    allowed=list(cr.CHOSEN_FROM_VALUES),
                )
            if not _is_storable_value(chosen_value):
                return _conflict_refusal(
                    "unrepresentable_value",
                    (
                        "This value could not be stored intact — it is too large, "
                        "too deeply nested, or contains something JSON cannot "
                        "represent — so a record containing it could not be read "
                        "back. It is REFUSED rather than reshaped. Nothing was "
                        "written."
                    ),
                )
            if (
                chosen_from == cr.CHOSEN_FROM_CANDIDATE
                and evidence_classify.canonical_answer(chosen_value) not in competing
            ):
                return _conflict_refusal(
                    "chosen_value_not_a_candidate",
                    (
                        "`chosen_from` says the value is one of the answers already "
                        "recorded against this address, and it is not one of them. A "
                        "value nothing asserted is an `edited` decision; labelling "
                        "it `candidate` would attribute it to a citation that does "
                        "not carry it. Nothing was written."
                    ),
                    address=address,
                    candidate_count=len(competing),
                )
        elif chosen_value is not None or chosen_from is not None:
            return _conflict_refusal(
                "deferred_carries_no_choice",
                (
                    "A deferred outcome records that nobody chose, so it carries "
                    "neither a chosen value nor a `chosen_from`. Storing a choice "
                    "under an outcome that says none was made would make the "
                    "outcome unreadable. Nothing was written."
                ),
            )

        precondition = _check_if_match(if_match, exp)
        if precondition is not None:
            return precondition

        at = _now_iso()
        stored, _unreadable = cr.resolutions_from_draft(exp.draft)
        existing = cr.find(stored, address, run_id)
        try:
            if existing is None:
                resolution = cr.new_resolution(
                    resolution_id=new_record_id(),
                    address=address,
                    outcome=outcome,
                    competing_values=competing,
                    recorded_utc=at,
                    # THE ACTOR SEAM STAYS UNSET, and that is the honest answer
                    # rather than a gap. This deployment establishes nobody: no
                    # shipped verifier reads a request, and the trusted
                    # authentication boundary that would make an arriving edge
                    # identity worth anything has not been built. A subject beside
                    # a recognised basis would be a name nothing vouched for, and
                    # the model refuses that shape outright.
                    trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
                    run_id=run_id,
                    chosen_value=chosen_value,
                    chosen_from=chosen_from,
                    rationale=rationale,
                )
            else:
                # REVISING APPENDS. The superseded value and the answer set it was
                # chosen from are kept on the appended transition, so every version
                # of the decision stays recoverable. `trust_basis` is deliberately
                # not passed: whether this deployment could attribute the caller is
                # not a change to the decision.
                resolution = cr.revise_resolution(
                    existing,
                    at=at,
                    outcome=outcome,
                    competing_values=competing,
                    chosen_value=chosen_value,
                    chosen_from=chosen_from,
                    rationale=rationale,
                )
        except cr.UnsupportedResolution as refusal:
            # THE MODEL'S OWN REFUSALS REACH THE CLIENT AS A TYPED 422, NEVER A 500.
            # The checks above cover every shape a client can send; this covers the
            # ones only the model knows, so a malformed payload can never escape as
            # a traceback.
            return _conflict_refusal("unsupported_resolution", str(refusal))

        cr.write_resolution(exp.draft, resolution)
        _changed, stale = _save_versioned(exp, if_match)
        if stale is not None:
            return stale  # another writer won the race; this decision was not stored
        response.headers["ETag"] = exp.etag()
        return {
            "resolution": cr.resolution_view(resolution, competing),
            "experiment_version": exp.version_token(),
        }


# --- 13. source preview -------------------------------------------------------


@router.get(
    "/experiments/{experiment_id}/source-preview",
    tags=[TAG_EVIDENCE],
    summary="Preview a Cited Source File",
    description=(
        "The text of one committed reference source file, line by line, "
        "together with the one-based line numbers this record's evidence actually "
        "cites in it. Read-only.\n\n"
        "Only the two committed reference files may be previewed. A name "
        "containing a path separator or a traversal fragment is rejected, and any "
        "other filename is refused with the allowed names listed in the response. "
        "The file that cites fields rather than lines yields no cited line "
        "numbers, which is expected rather than an error."
    ),
    response_description="The file's lines, its media type, and the cited line numbers.",
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        400: {
            "description": (
                "The `source` name is not a bare filename — it contains a path "
                "separator or a traversal fragment. Nothing was read."
            )
        },
        404: {
            "description": (
                "Either no experiment has that id, or the `source` name is a bare "
                "filename outside the two-file allowlist. The allowed names are "
                "listed in the refusal."
            )
        },
    },
)
def get_source_preview(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    source: Annotated[
        str,
        Query(
            description=(
                "The bare filename of a committed reference file. A path, a "
                "traversal fragment, or any name outside the allowlist is refused."
            )
        ),
    ] = "",
):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    try:
        return sources.read_source(source, exp)
    except sources.SourceTraversal:
        return JSONResponse(
            status_code=400,
            content={
                "error": "unsafe_source_name",
                "message": "Path traversal rejected — pass a bare filename.",
            },
        )
    except sources.SourceNotAllowed:
        return JSONResponse(
            status_code=404,
            content={
                "error": "source_not_allowed",
                # Slice 2A: was "…may be previewed in this synthetic prototype."
                # Same defect class as the `_UPLOAD_BLOCKED` reason above — the
                # FACT is preview-scoped and still true, but the adjectival
                # "in this synthetic prototype" labelled the whole deployment,
                # which now also runs a read-only diagnostic over an isolated
                # test database. This is the wording the operation's own
                # description already carries, so the two cannot drift.
                "message": "Only the two committed reference files may be previewed.",
                "allowed": list(ws.SOURCE_FILES),
            },
        )


# --- 13b. artifacts (exported record + sidecar content, read-only) ------------


@router.get(
    "/experiments/{experiment_id}/artifacts",
    tags=[TAG_EXPORT],
    summary="Get a Record's Exported Artifacts",
    description=(
        "The official ISAAC record and the evidence-sidecar JSON that this "
        "record's export wrote, plus their filenames as bare basenames — never a "
        "server path.\n\n"
        "Both files are resolved from the record id, never from a caller-supplied "
        "path. A record that has not been exported yet returns `200` with null "
        "payloads rather than an error. Read-only.\n\n"
        "A record with **runs** exports one official record per run and has no "
        "single pair of its own, so this operation returns null payloads for it "
        "together with a `reason` saying why. Those per-run files are not listed "
        "here yet."
    ),
    response_description=(
        "The record and sidecar JSON with their filenames, or nulls when nothing "
        "has been exported."
    ),
    responses={**_R_STORAGE_UNAVAILABLE, **_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def get_artifacts(scope: TutorialScopeDep, experiment_id: ExperimentId):
    """Return the written record + sidecar JSON for an exported experiment.

    Read-only: it reads ONLY the two files ``export`` wrote inside the workspace,
    resolved from the record id (never a query-controlled path). A non-exported
    experiment returns null payloads (200, not an error); an unknown id is 404.

    P4 — an artifact that is MISSING or unreadable while the state says exported is
    also a ``200`` with a null payload for that file, never a raise. The response
    additionally carries ``artifact``: the SAME derived
    ``{"state": "none"|"current"|"stale", "reason": …}`` block the detail endpoint
    serves under the same key (``_detail`` -> ``dependencies.artifact_state``), so a
    caller can tell "never exported" (``none``) from "exported but the artifact is
    gone" (``stale``) — two situations that would otherwise both look like a null
    payload. No new vocabulary is introduced and the reason string has one
    definition (``dependencies.MISSING_REASON``).

    ``200`` rather than ``404`` because the *record* exists and is being described;
    only one of its files is absent. A 404 would say the record is unknown, which is
    false, and would also lose the ``artifact`` distinction above.
    """
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    if not exp.exported():
        payload = {
            "record": None,
            "sidecar": None,
            "record_filename": None,
            "sidecar_filename": None,
            # Single-sourced: for a non-exported record this is
            # {"state": "none", "reason": None}.
            "artifact": dependencies.artifact_state(exp),
        }
        if exp.runs:
            # A fan-out reaches here with `artifact.state` possibly `current` — the
            # per-run records ARE on disk and current — beside four nulls, which on
            # its own reads as "current, but there is nothing". This route still
            # serves the experiment's OWN pair and a fan-out has none, so the nulls
            # are correct and the missing piece is the explanation. Listing the
            # per-run pairs is the Run-workspace slice's job (it is the slice with a
            # UI for them); saying so is this one's.
            payload["reason"] = FAN_OUT_ARTIFACT_REASON
        return payload
    record_path = exp.record_path()
    sidecar_path = exp.sidecar_path()
    record = _read_artifact_json(record_path)
    sidecar = _read_artifact_json(sidecar_path)
    # `artifact_state` only judges the RECORD file, so a readable record with an
    # absent sidecar would report `current` — true of the record, silent about the
    # half that is gone. Force `stale` whenever EITHER file failed to read, so the
    # block never implies a complete artifact pair that is not on disk.
    if record is None or sidecar is None:
        artifact = {"state": "stale", "reason": dependencies.MISSING_REASON}
    else:
        artifact = dependencies.artifact_state(exp)
    return {
        "record": record,
        "sidecar": sidecar,
        # P30.6 — SAFE basename only, never the absolute server/mount path. Reported
        # even when the file is absent: it names what the export wrote (matching
        # `_detail.artifact_refs`, which also keys off `exported()` rather than
        # existence) and a basename leaks nothing.
        "record_filename": record_path.name,
        "sidecar_filename": sidecar_path.name,
        "artifact": artifact,
    }


# --- 14. graph status (memory plane) ------------------------------------------


#: Additive /graph/status count fields sourced from the memory reader's overview.
#: Single-source guarantee: the separated status fields and these counts describe
#: the SAME graph — the handler resolves ONE reader and reads both its
#: ``status()`` and its ``overview()`` off that one instance. Present with real
#: values when the reader is available; explicit ``null`` (not omitted, for shape
#: stability) otherwise. (``source_graph_commit`` carries the built_at_commit as a
#: top-level version-metadata field, so it is not repeated here.)
_STATUS_ADDITIVE_FIELDS = (
    "node_count", "edge_count", "community_count",
    "file_count", "concept_count", "graph_mtime",
)

#: Memory-plane notes (P24.10). Leads/provenance framing only — never
#: PASS/FAIL/valid/invalid/verdict wording, and never phrased around a single
#: conflated freshness status (there isn't one anymore). Keyed by availability.
_GRAPH_STATUS_NOTES = {
    "available": (
        "Project Memory provides leads and provenance, never a correctness "
        "ruling — confirm every lead against the cited files."
    ),
    "unavailable": (
        "Project Memory is unavailable, so no leads can be served. It provides "
        "leads and provenance, never a correctness ruling — confirm against the "
        "cited files."
    ),
}


@router.get(
    "/graph/status",
    tags=[TAG_GRAPH],
    summary="Get Project Memory Status",
    description=(
        "Provider-agnostic status for the Project Memory plane: whether it is "
        "available, the integrity of its artifact, the provider serving it, "
        "whether its indexing policy is consistent, the freshness of its indexed "
        "sources together with the scope and basis of that judgement, the policy "
        "and served-manifest fingerprints, the served file count, and the snapshot "
        "schema version. Node, edge, community, file and concept counts are "
        "included when a graph is readable and are explicit nulls otherwise, so "
        "the response shape never changes.\n\n"
        "The deployed app commit is reported as version metadata only and is never "
        "an input to any freshness judgement. A freshness status that cannot be "
        "proven is reported as unknown rather than assumed current.\n\n"
        "Project Memory provides leads and provenance to confirm against the cited "
        "files, never a correctness ruling. Read-only."
    ),
    response_description="The separated memory-plane status, with counts when a graph is readable.",
    responses={**_R_UNAUTHORIZED},
)
def graph_status() -> dict:
    """Provider-agnostic, separated memory-plane status (P24.10).

    Resolves ONE reader and reads BOTH its ``status()`` (provider identity +
    separated availability / integrity / provable freshness) and its
    ``overview()`` (counts) off that same instance — never
    ``isinstance``-branches on which provider it is.

    App-HEAD equality is REMOVED from all freshness: the deployed commit is
    surfaced ONLY as ``deployed_app_commit`` version metadata, never an input to
    ``memory_policy`` or ``indexed_sources``. The two freshness concepts are kept
    separate and provable; the reader returns ``"unknown"`` rather than
    manufacturing ``"current"`` when it cannot prove a status.
    """
    reader = memory.get_default_reader()
    st = reader.status()
    overview = reader.overview()

    available = st["available"]
    availability = "available" if available else "unavailable"
    note = _GRAPH_STATUS_NOTES["available" if available else "unavailable"]

    body = {
        "plane": "memory",
        "availability": availability,
        "integrity": st["integrity"],
        "provider": st["provider_kind"] if available else "unavailable",
        "memory_policy": st["policy_consistency"],
        "indexed_sources": st["indexed_sources"],
        "policy_fingerprint": st["policy_fingerprint"],
        "served_manifest_fingerprint": st["served_manifest_fingerprint"],
        "served_file_count": st["served_file_count"],
        "freshness_scope": st["freshness_scope"],
        "freshness_basis": st["freshness_basis"],
        "source_graph_commit": st["source_graph_commit"],
        "snapshot_schema_version": st["snapshot_schema_version"],
        # VERSION METADATA ONLY — never a freshness input.
        "deployed_app_commit": _build_commit(),
        "note": note,
    }
    if overview["available"]:
        body.update(
            node_count=overview["node_count"],
            edge_count=overview["edge_count"],
            community_count=overview["community_count"],
            file_count=overview["served_file_count"],
            concept_count=overview["concept_count"],
            graph_mtime=overview["graph_mtime"],
        )
    else:
        body.update({key: None for key in _STATUS_ADDITIVE_FIELDS})
    return body


# --- 15. uploads (always blocked) ---------------------------------------------


@router.post(
    "/uploads",
    tags=[TAG_UPLOADS],
    summary="Refuse a File Upload (Governance Seam)",
    description=(
        "Always refuses with `403`. This is the write side of the synthetic-only "
        "governance boundary: no multipart form is declared or parsed, and no file "
        "is read, inspected, or stored. The refusal carries the reason and the "
        "current synthetic-only flag so a client can explain the boundary to a "
        "user.\n\n"
        "Real or private data ingestion is approval-gated and is not enabled in "
        "this prototype."
    ),
    response_description=(
        "Not produced by this operation — every request is refused with the `403` "
        "documented below."
    ),
    responses={
        **_R_UNAUTHORIZED,
        403: {
            "description": (
                "The refusal, with the reason and the current synthetic-only flag. "
                "The upload itself is never accepted; a request that reaches the "
                "handler always lands here. When the deployment enables API-key "
                "authentication, an unauthenticated request is rejected with the "
                "`401` above before it reaches this refusal."
            )
        },
    },
)
def uploads():
    # Governance seam: no multipart is declared or parsed; no file is read or stored.
    # The refusal is tied to the authoritative runtime-mode source; uploads stay
    # blocked in synthetic-only mode (real-data ingestion is Phase 31, not here).
    payload = dict(_UPLOAD_BLOCKED)
    payload["synthetic_only"] = ws.is_synthetic_only()
    return JSONResponse(status_code=403, content=payload)


# --- 16. memory (project memory plane over HTTP) -------------------------------
#
# Thin HTTP wrapper around the read-only ``isaac_api.memory`` reader (P24.1).
# Handlers call ONLY the reader (plus FastAPI plumbing) — no isaac_records
# imports, no verdict computation. The reader never raises for artifact
# problems, so these handlers never need a try/except to avoid a 500.

MEMORY_NOTE = "Project memory returns leads to verify — never a validation verdict."


def _memory_error(status_code: int, error: str, **extra) -> JSONResponse:
    content = {"error": error, "plane": "memory", "note": MEMORY_NOTE}
    content.update(extra)
    return JSONResponse(status_code=status_code, content=content)


@router.get(
    "/memory/concepts",
    tags=[TAG_MEMORY],
    summary="List Project Memory Concepts",
    description=(
        "The concepts Project Memory has indexed, each with the label and summary "
        "metadata the reader exposes.\n\n"
        "When no graph is readable this returns `200` with `available: false`, a "
        "stable machine-readable reason, and an empty list — never an error status "
        "and never a fabricated concept. Read-only. Project Memory returns leads "
        "to verify, never a validation verdict."
    ),
    response_description="The indexed concepts, or an honest unavailable envelope.",
    responses={**_R_UNAUTHORIZED},
)
def get_memory_concepts() -> dict:
    reader = memory.get_default_reader()
    overview = reader.overview()
    if not overview["available"]:
        return {
            "plane": "memory",
            "note": MEMORY_NOTE,
            "available": False,
            "reason": overview["reason"],
            "concepts": [],
        }
    return {
        "plane": "memory",
        "note": MEMORY_NOTE,
        "available": True,
        "concepts": reader.concepts(),
    }


@router.get(
    "/memory/concepts/{concept_id}",
    tags=[TAG_MEMORY],
    summary="Get One Project Memory Concept",
    description=(
        "One concept's detail together with the files and other concepts related "
        "to it.\n\n"
        "When no graph is readable this returns `200` with `available: false` and a "
        "null concept: availability is reported before identity, because the set of "
        "valid ids cannot be known without a graph, so an unknown id is only ever "
        "reported once the graph is known to be readable. Read-only; leads to "
        "verify, never a verdict."
    ),
    response_description="The concept and its related files and concepts.",
    responses={
        **_R_UNAUTHORIZED,
        404: {
            "description": (
                "The graph is readable but holds no concept with that id."
            )
        },
    },
)
def get_memory_concept(
    concept_id: Annotated[
        str,
        Path(
            description=(
                "A concept id as listed by `GET /api/memory/concepts`."
            )
        ),
    ],
):
    reader = memory.get_default_reader()
    overview = reader.overview()
    if not overview["available"]:
        return {
            "plane": "memory",
            "note": MEMORY_NOTE,
            "available": False,
            "reason": overview["reason"],
            "concept": None,
            "related": {"files": [], "concepts": []},
        }
    # Availability wins over 404 — we cannot know the id set without a graph,
    # so an unknown id is only ever reported once we know the graph is readable.
    detail = reader.concept(concept_id)
    if detail is None:
        return _memory_error(404, "concept_not_found", id=concept_id)
    related = detail.pop("related")
    return {
        "plane": "memory",
        "note": MEMORY_NOTE,
        "available": True,
        "concept": detail,
        "related": related,
    }


@router.get(
    "/memory/files",
    tags=[TAG_MEMORY],
    summary="List Indexed Project Memory Files",
    description=(
        "The repository files Project Memory has indexed and is allowed to serve, "
        "each with the metadata the reader exposes for it.\n\n"
        "When no graph is readable this returns `200` with `available: false`, a "
        "stable reason, and an empty list. Read-only; leads to verify, never a "
        "verdict."
    ),
    response_description="The indexed served files, or an honest unavailable envelope.",
    responses={**_R_UNAUTHORIZED},
)
def get_memory_files() -> dict:
    reader = memory.get_default_reader()
    overview = reader.overview()
    if not overview["available"]:
        return {
            "plane": "memory",
            "note": MEMORY_NOTE,
            "available": False,
            "reason": overview["reason"],
            "files": [],
        }
    return {
        "plane": "memory",
        "note": MEMORY_NOTE,
        "available": True,
        "files": reader.files(),
    }


@router.get(
    "/memory/file",
    tags=[TAG_MEMORY],
    summary="Get One Indexed File's Memory Entry",
    description=(
        "One indexed file's detail, the files and concepts related to it, and the "
        "rationales recorded for those relationships.\n\n"
        "An unsafe path is rejected regardless of whether a graph is readable, "
        "because that guard is deterministic and does not depend on the graph. A "
        "safe path that is simply not indexed is reported as not found once the "
        "graph is known to be readable. Read-only; leads to verify, never a "
        "verdict."
    ),
    response_description="The file's detail, its relations, and their rationales.",
    responses={
        **_R_UNAUTHORIZED,
        400: {
            "description": (
                "The `path` is not a safe repository-relative path. Nothing was "
                "read, and this is reported even when no graph is available."
            )
        },
        404: {
            "description": (
                "The graph is readable but does not index that path."
            )
        },
    },
)
def get_memory_file(
    path: Annotated[
        str,
        Query(
            description=(
                "A repository-relative path of an indexed served file, as listed "
                "by `GET /api/memory/files`."
            )
        ),
    ] = "",
):
    reader = memory.get_default_reader()
    # Unsafe path is a deterministic, availability-independent guard: it wins
    # even when the graph is absent (spec §3.5).
    classification = reader.classify_path(path)
    if classification == "unsafe":
        return _memory_error(400, "unsafe_source_path", path=path)

    overview = reader.overview()
    if not overview["available"]:
        return {
            "plane": "memory",
            "note": MEMORY_NOTE,
            "available": False,
            "reason": overview["reason"],
            "file": None,
            "related": {"files": [], "concepts": []},
            "rationales": [],
        }
    if classification == "not_indexed":
        return _memory_error(404, "source_not_indexed", path=path)

    detail = reader.file(path)
    related = detail.pop("related")
    rationales = detail.pop("rationales")
    return {
        "plane": "memory",
        "note": MEMORY_NOTE,
        "available": True,
        "file": detail,
        "related": related,
        "rationales": rationales,
    }


@router.get(
    "/memory/graph",
    tags=[TAG_GRAPH],
    summary="Get the Project Memory Graph Projection",
    description=(
        "A deterministic, capped projection of the served-file reference graph: "
        "nodes, undirected deduplicated edges, communities, and the provenance of "
        "the projection. Every element is derived from the Project Memory reader's "
        "public surface, so it describes the same graph the status operation "
        "reports on.\n\n"
        "When no graph is readable it returns an honest envelope with "
        "`available: false` and zero nodes and edges rather than a fabricated "
        "graph. Read-only; leads to verify, never a verdict."
    ),
    response_description="The nodes, edges, communities, and provenance of the projection.",
    responses={**_R_UNAUTHORIZED},
)
def get_memory_graph() -> dict:
    """P36.2 — the Project Memory "Graph" tab: a deterministic, capped,
    served-file reference projection (nodes/edges/communities) derived purely
    from the reader's public surface. See ``memory_graph.build_graph_projection``
    for the full algorithm; this handler never needs a try/except — that
    function never raises."""
    return memory_graph.build_graph_projection(memory.get_default_reader())


@router.get(
    "/memory/graph/detail",
    tags=[TAG_GRAPH],
    summary="Get the Symbol-Level Project Memory Graph Structure",
    description=(
        "The symbol-level structure of the source graph: the individual symbols, "
        "document sections, and recorded rationales inside each served file, the "
        "relations between them, and their community grouping. Every node, "
        "relation, and direction is the source graph's own value, passed through "
        "verbatim.\n\n"
        "This is a point-in-time index, not a map of today's code. The structure "
        "describes the commit reported as `built_at_commit`, which is generally "
        "**not** the current repository head, and the response says so "
        "machine-readably with `is_point_in_time: true` and "
        "`describes_current_head: false`. Content freshness and structural "
        "freshness are separate axes: the served-file content manifest is kept "
        "current, while this structure stays pinned to the commit that was "
        "indexed, and `served_set_consistency` reports whether the two still "
        "describe the same set of served files.\n\n"
        "Scoped to served files only — a symbol whose owning file is not served "
        "is absent, never partially disclosed. Served separately from the graph "
        "projection operation because it is much larger and is fetched only on "
        "demand; that operation's own response is unaffected by this one.\n\n"
        "When the artifact is absent or unreadable it returns an honest envelope "
        "with `available: false` and zero nodes and edges rather than a "
        "fabricated graph, and its provenance collapses to nulls rather than to "
        "plausible-looking defaults. Read-only; leads to verify, never a verdict."
    ),
    response_description=(
        "The symbol-level nodes, their relations, community names, and the "
        "point-in-time provenance of the structure."
    ),
    responses={**_R_UNAUTHORIZED},
)
def get_memory_graph_detail() -> dict:
    """The deep (symbol-level) memory-graph layer: a SEPARATE, lazily-fetched
    endpoint over the committed graph-detail artifact. Deliberately not folded
    into ``get_memory_graph`` — the base served-file projection's response shape
    stays untouched. See ``memory_graph.build_graph_detail``; this handler needs
    no try/except, because that function never raises (HTTP 200 always)."""
    return memory_graph.build_graph_detail(
        memory.get_default_detail_source(), memory.get_default_reader()
    )


# --- 17. search (composed truth + memory planes, grouped, no verdict) ----------
#
# Composes the two existing search cores into ONE grouped, plane-labeled envelope.
# It computes NO verdict and carries NO verdict keys. Each plane is a separate,
# self-labeled group so a client always knows which plane a lead came from and can
# never confuse a memory lead for a truth-plane ruling.
#
# Degradation is ALWAYS in-body (available:false + reason), never a 5xx: both cores
# are designed never to raise, and the composition is additionally wrapped so any
# unexpected failure still yields a shaped 200 with the affected group degraded.
#
# ``scope`` selects which planes are actually searched:
#   * ``all``       -> both planes searched and populated.
#   * ``workspace`` -> workspace searched; memory group PRESENT with its real
#                      availability reported but no rows (memory not searched).
#   * ``memory``    -> symmetric: memory searched; workspace group present, no rows.
# ``normalized_query`` is always computed (workspace_search is cheap over the tens of
# in-memory snapshots) even when the workspace group's rows are blanked out.

_SEARCH_SCOPES = ("all", "workspace", "memory")


def _searched_scope_reason(reason: str | None, hydration: ws.HydrationOutcome) -> str | None:
    """The workspace group's ``reason``, with one ASSERTION withheld when it is unsafe.

    ``scope_has_no_records`` IS NOT "no rows matched" — it exists precisely to be
    STRONGER than ``total: 0``. Its own definition (``search.SCOPE_HAS_NO_RECORDS``)
    is "the scope searched holds NO RECORDS AT ALL", and the reason it was added is
    to stop a reader rephrasing a query that was never going to match anything.

    Which makes it the one thing on this route that a short snapshot turns into a
    false statement. When hydration could not finish, the search core is handed
    whatever working copies exist and correctly reports that IT saw none — but "the
    search core saw no records" and "there are no records" are different claims,
    and only the second one reaches a person. Measured on this branch before the
    fix: two durable rows that ``GET /api/experiments`` was simultaneously flagging
    as possibly missing, and ``GET /api/search`` answering
    ``{"available": true, "reason": "scope_has_no_records", "total": 0}``.

    SO THE CLAIM IS DROPPED, NOT REPLACED. A bare ``total: 0`` understates — it
    says nothing about whether anything exists — and understating is the safe
    direction here. Inventing a third reason label would be a contract change and a
    new thing for every client to learn, for a state the list response already
    describes in full.

    ``query_too_short`` IS DELIBERATELY LEFT ALONE. It is a fact about the REQUEST
    and is true whatever the scope holds.
    """
    if reason == search.SCOPE_HAS_NO_RECORDS and not hydration.complete:
        return None
    return reason


def _blank_group_rows(group: dict) -> dict:
    """Report a group's availability/reason but with no rows (out-of-scope plane)."""
    group["results"] = []
    group["total"] = 0
    group["returned"] = 0
    return group


@router.get(
    "/search",
    tags=[TAG_SEARCH],
    summary="Search the Workspace and Project Memory",
    description=(
        "One grouped envelope with two independently reported groups: `workspace` "
        "(truth-plane leads from the experiment snapshot) and `memory` (advisory "
        "Project Memory leads). Each group carries its own plane label, provider, "
        "availability, reason, totals and pagination, so a memory lead can never "
        "be mistaken for a truth-plane ruling, and one group's failure never "
        "affects the other.\n\n"
        "The envelope computes no verdict, and a plane that cannot answer degrades "
        "inside the `200` body rather than returning an error status. Read-only; it "
        "reshapes only content the read operations already expose."
    ),
    response_description="The normalised query, the scope applied, and the two plane groups.",
    responses={**_R_UNAUTHORIZED, **_R_TUTORIAL_SCOPE},
)
def search_records(
    # NOT named ``scope``: this operation already has a ``scope`` query parameter
    # selecting which PLANES to search, which is an unrelated meaning.
    tutorial_session: TutorialScopeDep,
    q: Annotated[
        str,
        Query(
            description=(
                "The search text. It is truncated to 256 characters before "
                "normalisation, and a query shorter than two normalised characters "
                "returns no rows with the reason `query_too_short` in both groups. "
                "When the workspace being searched holds no records at all, the "
                "`workspace` group reports the reason `scope_has_no_records` — "
                "distinct from a query that simply matched nothing. That reason is "
                "WITHHELD, leaving a bare `total: 0`, whenever this read could not "
                "restore every stored working copy (the state "
                "`GET /api/experiments` reports as `incomplete`): 'there is "
                "nothing here' is a stronger claim than a short snapshot can "
                "support."
            )
        ),
    ] = "",
    scope: Annotated[
        str,
        Query(
            description=(
                "Which planes are actually searched: `all` (the default), "
                "`workspace`, or `memory`. The out-of-scope group is still present "
                "and still reports its real availability, but carries no rows. An "
                "unrecognised value falls back to `all`."
            )
        ),
    ] = "all",
    limit: Annotated[
        int,
        Query(
            description=(
                "Maximum rows to return per group. Clamped into the range 0 to 50; "
                "the value actually applied is echoed in each group."
            )
        ),
    ] = 10,
    offset: Annotated[
        int,
        Query(description="Number of rows to skip within each group."),
    ] = 0,
) -> dict:
    if scope not in _SEARCH_SCOPES:
        scope = "all"

    # --- workspace group (truth plane) ---
    # Always run the workspace core: it is cheap over the in-memory snapshot and it
    # is the source of the envelope's ``normalized_query``. Only its rows are blanked
    # when the workspace plane is out of scope.
    normalized_query = search.normalize((q or "")[:256])
    query_too_short = False
    try:
        # WITH the hydration outcome, because ONE of this group's reasons is an
        # assertion about the world rather than about the query. See
        # ``_searched_scope_reason``.
        exps, hydration = ws.list_experiments_with_hydration(tutorial_session)
        wres = search.workspace_search(q, exps, limit=limit, offset=offset)
        normalized_query = wres.normalized_query
        query_too_short = wres.reason == search.QUERY_TOO_SHORT
        workspace_group = {
            "plane": search.PLANE,
            "provider": search.PROVIDER,
            "available": True,
            "reason": _searched_scope_reason(wres.reason, hydration),
            "total": wres.total,
            "returned": wres.returned,
            "limit": wres.limit,
            "offset": wres.offset,
            "results": [dataclasses.asdict(r) for r in wres.results],
        }
    except Exception:  # pragma: no cover - defensive; degrade in-body, never 500
        workspace_group = {
            "plane": search.PLANE,
            "provider": search.PROVIDER,
            "available": False,
            "reason": None,
            "total": 0,
            "returned": 0,
            "limit": max(0, limit),
            "offset": max(0, offset),
            "results": [],
        }
    if scope == "memory":
        _blank_group_rows(workspace_group)

    # --- memory group (memory plane) ---
    try:
        reader = memory.get_default_reader()
        mres = reader.search(q, limit=limit, offset=offset)
        try:
            provider_kind = reader.status().get("provider_kind")
        except Exception:  # pragma: no cover - defensive; identity only
            provider_kind = None
        memory_group = {
            "plane": "memory",
            # Coalesce a missing kind to "unavailable" so the label is never the
            # literal "memory:None" (only reachable if status() unexpectedly raises).
            "provider": f"memory:{provider_kind or 'unavailable'}",
            "note": MEMORY_NOTE,
            "available": mres["available"],
            "reason": mres["reason"],
            "total": mres["total"],
            "returned": mres["returned"],
            "limit": mres["limit"],
            "offset": mres["offset"],
            "results": mres["results"],
        }
    except Exception:  # pragma: no cover - defensive; degrade in-body, never 500
        memory_group = {
            "plane": "memory",
            "provider": "memory:unavailable",
            "note": MEMORY_NOTE,
            "available": False,
            "reason": "graph_unreadable",
            "total": 0,
            "returned": 0,
            "limit": max(0, limit),
            "offset": max(0, offset),
            "results": [],
        }
    # A too-short query is a QUERY-level condition, orthogonal to plane
    # availability: the workspace core reports it directly, but the memory core
    # checks availability first and so would surface ``graph_absent`` for a short
    # query against an absent graph. Normalize both planes to the same query-level
    # ``query_too_short`` reason (with no rows) so the envelope is symmetric — the
    # plane's own ``available`` flag still reports its true state.
    if query_too_short:
        memory_group["reason"] = search.QUERY_TOO_SHORT
        _blank_group_rows(memory_group)

    if scope == "workspace":
        _blank_group_rows(memory_group)

    return {
        "query": q,
        "normalized_query": normalized_query,
        "scope": scope,
        "workspace": workspace_group,
        "memory": memory_group,
    }


# --- 18. runtime records (thin read-only cross-record projection, P30.1) -------
#
# A DERIVED read model over the SAME ``list_experiments()`` snapshot search uses —
# no index, no cache, no lock, current-by-construction. It emits ONLY the safe
# confirmed-facts allow-set (see ``runtime_records``) plus freshness metadata, and
# accepts a few typed filters the cross-record triage consumer uses. Auth is
# enforced by the app-wide middleware exactly like the other reads (401 when the
# key is set). It never mutates and never touches the truth path.


@router.get(
    "/runtime/records",
    tags=[TAG_EXPERIMENTS],
    summary="List a Cross-Record Triage Projection",
    description=(
        "A derived read model over the same experiment snapshot the search "
        "operation uses, for triaging many records at once. Each row carries only a "
        "fixed safe set of confirmed facts: the experiment id, title, derived "
        "status, open-question count, exported flag, exported record id, a minimal "
        "workflow summary, the five-class evidence histogram as counts only, the "
        "exported-artifact freshness state, the current revision, the last update "
        "time, and a client route to open the record. No field value, evidence "
        "body, source locator, or filesystem path appears.\n\n"
        "`total` is the filtered count taken before pagination, so a client can "
        "page without losing the denominator. Rows are ordered deterministically. "
        "Computed fresh on every call — no index, no cache, no lock, and no "
        "mutation."
    ),
    response_description="The projected rows and the filtered total before pagination.",
    responses={**_R_UNAUTHORIZED, **_R_TUTORIAL_SCOPE},
)
def runtime_record_projection(
    scope: TutorialScopeDep,
    status: Annotated[
        str | None,
        Query(
            description=(
                "Keep only records whose derived status equals this value exactly. "
                "Omit for no status filter."
            )
        ),
    ] = None,
    workflow_state: Annotated[
        str | None,
        Query(
            description=(
                "Keep only records in this workflow state: `blocked`, `reopened`, "
                "or `current`. An unrecognised value matches nothing rather than "
                "being ignored, so a bad filter never returns the full set."
            )
        ),
    ] = None,
    artifact: Annotated[
        str | None,
        Query(
            description=(
                "Keep only records with this exported-artifact freshness: `none`, "
                "`current`, or `stale`. An unrecognised value matches nothing."
            )
        ),
    ] = None,
    has_conflict: Annotated[
        bool,
        Query(
            description=(
                "When true, keep only records with at least one field classified "
                "as conflicting evidence."
            )
        ),
    ] = False,
    limit: Annotated[
        int | None,
        Query(
            description=(
                "Maximum rows to return after filtering. Omit to return every "
                "filtered row."
            )
        ),
    ] = None,
    offset: Annotated[
        int,
        Query(description="Number of filtered rows to skip before returning any."),
    ] = 0,
) -> dict:
    filters = {
        "status": status,
        "workflow_state": workflow_state,
        "artifact": artifact,
        "has_conflict": has_conflict,
    }
    # Fresh scan each call → project → filter. ``total`` is the filtered count
    # BEFORE pagination so a client can page without losing the denominator.
    records = runtime_records.project_records(ws.list_experiments(scope), filters=filters)
    total = len(records)
    start = max(0, offset)
    records = records[start:]
    if limit is not None:
        records = records[: max(0, limit)]
    return {"records": records, "total": total}


# --- 19. assistant query (READ-ONLY deterministic resolver, P34.1) -------------
#
# A free-form question is classified against a finite intent catalog and answered
# from grounding this route assembles read-only from the loaded experiment. It is
# subordinate/advisory: it NEVER mutates a record, revision, workflow, evidence,
# validation, export, memory, or file; it never states a PASS/FAIL or a
# valid/invalid conclusion; and it never guesses a scientific value. The resolver
# module is stdlib-only and isaac_records-free (truth isolation, like memory.py) —
# the expensive grounding (the validate dry-run, the memory search) is supplied as
# thunks invoked only for the matched intent. Auth is the app-wide middleware.

#: A question longer than this is rejected (bounds the work; never truncated-and-answered).
_ASSISTANT_MAX_QUESTION = 500
#: History beyond this is ignored — it is presentation-only, never truth grounding.
_ASSISTANT_MAX_HISTORY = 20


class AssistantQueryRequest(BaseModel):
    """Typed assistant-query body. ``history`` is presentation-only (never truth)."""

    model_config = ConfigDict(extra="ignore")

    question: str
    grounded_rev: str | None = None
    history: list | None = None


def _assistant_validate_dryrun(exp: Experiment) -> dict:
    """The SAME read-only validation the ``/validate`` endpoint computes, as a
    thunk the resolver invokes only for an export intent. Writes nothing; never
    raises (mirrors ``post_validate``'s defensive dry-run).

    P4 review FIX C — "never raises" was FALSE for an exported record whose artifact
    was absent or corrupt: the read below was unguarded, so an assistant question with
    an export intent raised ``FileNotFoundError``. It now returns the SAME crash
    sentinel ``post_validate`` returns, which ``assistant_query``'s
    ``is_validation_unavailable`` check already routes to the honest
    "could not be completed" answer — so the assistant states no count, no location
    and no verdict, instead of describing a violation nobody located.

    REVIEW ITEM F1 — a record WITH RUNS is answered by ``_fan_out_official_verdict``,
    the same function ``post_validate`` returns. This branch did not exist, so the
    assistant fell through to the dry run below and validated ``exp.draft`` — the
    experiment-level half, which is never exported and is not a record — reporting
    ``'descriptors' is a required property`` about a set of records that had just
    passed official validation. The verdict is PROJECTED to the two keys this channel
    answers with: the assistant answers a question, it does not serve the validation
    contract, so widening it to carry ``schema``/``dry_run``/``runs`` would put a
    second copy of that contract on a surface with no consumer for it.
    """
    if exp.runs:
        verdict = _fan_out_official_verdict(exp)
        return {"ok": verdict["ok"], "errors": verdict["errors"]}
    if exp.exported():
        record = _read_artifact_json(exp.record_path())
        if record is None:
            _log.warning(
                "assistant validate: record %s is marked exported but its artifact "
                "could not be read; reporting no verdict",
                exp.id,
            )
            return {
                "ok": False,
                "errors": [{"path": "$", "message": "Validation could not be completed."}],
            }
        report = validate_official(record, REPO_ROOT)
        return {
            "ok": report.ok,
            "errors": [{"path": e.path, "message": e.message} for e in report.errors],
        }
    try:
        result = export_draft(exp.draft, REPO_ROOT)
        if result.official_report is not None:
            errors = [{"path": e.path, "message": e.message} for e in result.official_report.errors]
        elif not result.draft_report.ok:
            errors = [{"path": w, "message": m} for w, m in result.draft_report.errors]
        else:
            errors = []
        return {"ok": result.ok, "errors": errors}
    except Exception:
        _log.exception("assistant validate dry-run failed experiment=%s", exp.id)
        return {"ok": False, "errors": [{"path": "$", "message": "Validation could not be completed."}]}


#: Shared wording for the two assistant operations' request bodies.
_ASSISTANT_BODY_DESCRIPTION = (
    "`question` is required, must not be blank, and is capped at "
    f"{_ASSISTANT_MAX_QUESTION} characters — an over-long question is rejected, "
    "never truncated and answered. `grounded_rev` optionally states which record "
    "revision the question was asked against. `history` is presentation-only: at "
    f"most {_ASSISTANT_MAX_HISTORY} entries are kept and it never influences the "
    "answer."
)


@router.post(
    "/experiments/{experiment_id}/assistant/query",
    tags=[TAG_ASSISTANT],
    summary="Ask a Question About One Record",
    description=(
        "Answers a free-form question about this record by classifying it against "
        "a fixed, finite intent catalog and answering from grounding assembled "
        "read-only from what the API already exposes for the record: its summary, "
        "open blocking questions, evidence trail, workflow, revision, an in-memory "
        "validation dry run, and Project Memory search.\n\n"
        "There is no language model. A question outside the catalog, or one too "
        "ambiguous to route, is refused honestly rather than answered — it never "
        "guesses a scientific value.\n\n"
        "Read-only and advisory: it never changes the record, its revision, its "
        "workflow, its evidence, its validation, its export, Project Memory, or any "
        "file, and it never states a pass, fail, valid, or invalid conclusion. The "
        "response carries the record's unchanged `ETag`."
    ),
    response_description="The resolved answer with the grounding it was derived from, or an honest refusal.",
    responses={
        **_R_STORAGE_UNAVAILABLE,
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        400: {
            "description": (
                "The question is blank or exceeds the character limit. Nothing was "
                "classified or answered."
            )
        },
    },
)
def post_assistant_query(
    scope: TutorialScopeDep,
    experiment_id: ExperimentId,
    response: Response,
    req: AssistantQueryRequest = Body(..., description=_ASSISTANT_BODY_DESCRIPTION),
):
    # Typed input guards: an empty/whitespace or oversized question is rejected
    # with a stable typed error (never a 500, never the question text logged).
    question = req.question if isinstance(req.question, str) else ""
    if not question.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "empty_question", "message": "A non-empty question is required."},
        )
    if len(question) > _ASSISTANT_MAX_QUESTION:
        return JSONResponse(
            status_code=400,
            content={
                "error": "question_too_long",
                "message": f"The question exceeds the {_ASSISTANT_MAX_QUESTION}-character limit.",
            },
        )
    # history is presentation-only; cap it and never let it influence grounding.
    _ = (req.history or [])[:_ASSISTANT_MAX_HISTORY]

    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)

    # Classify FIRST (pure), then assemble only the read-only grounding needed —
    # the validate dry-run and the memory search are deferred behind thunks so an
    # intent that does not need them never pays for them.
    classified = assistant_query.classify(question)

    reader = memory.get_default_reader()
    ctx = assistant_query.AssistantContext(
        record_summary=_summary(exp),
        # The assistant reads only the queue's LENGTH and labels, never an answer
        # value, so the example channel is withheld outright here (the fail-closed
        # default). An assistant that cannot see an example answer cannot echo one.
        #
        # `entries=exp.pending()`, NOT `exp.draft` — THE LAST RUN-BLIND CALL SITE OF
        # `pending_to_list` IN THIS MODULE, and the only one that was still lying to a
        # person rather than to a screen. `GET /pending`, both `/answers` responses, the
        # run check and the run `/answers` response were all corrected to pass `entries`;
        # this one was not, so the assistant read `exp.draft["pending"]` — which
        # `Experiment.pending()` WITHHOLDS once a run exists, precisely because those
        # entries can no longer be answered anywhere. Measured over HTTP on a record
        # created through `POST /api/experiments`, one run, every run-level question
        # answered ON THE RUN::
        #
        #     exp.pending()                    -> 0        export_ready() -> True
        #     GET /pending                     -> 0
        #     GET /experiments/{id}            -> pending_count 0
        #     pending_to_list(exp.draft, ...)  -> 3   ['series', 'qc', 'descriptor']
        #
        #     "Is this record ready to export?"
        #        -> "... On this record, 3 fields still need you."
        #     "What fields are still pending?"
        #        -> "3 fields still need you: reduced_spectrum, qc_status,
        #            required_for_evidence_record."
        #     POST /answers {"series": ...}    -> 409 belongs_to_a_run
        #
        # So on a FINISHED record the assistant named three outstanding fields that were
        # each already answered on the run AND unanswerable at the record level by
        # design. It also contradicted ITSELF in the same session: the `record` intent
        # reads `_summary(exp)["pending_count"]`, which is `exp.pending_count()` and was
        # already run-aware, so "summarize this record" said 0 pending in the same
        # breath as "what still needs me?" said 3.
        #
        # A zero-run record's list is byte-identical either way (`Experiment.pending()`
        # returns `own` unchanged when `self.runs` is empty), so every seeded scenario
        # and every existing assistant answer is unmoved.
        #
        # COHERENCE FOR A MULTI-RUN RECORD is `assistant_query._pending_labels`'
        # responsibility, not this call site's: the entries carry `run_id`/`run_label`
        # (serialize keeps the tag for exactly this reason), and three runs each needing
        # a spectrum produce three byte-identical `about` values. Composing the run into
        # the label is done there, where the prose is composed, rather than by rewriting
        # entries here.
        pending=serialize.pending_to_list(
            exp.draft, ws.load_demo_answers(), entries=exp.pending()
        ),
        evidence_trail=serialize.evidence_trail_from_draft(exp.draft),
        workflow=_workflow_for(exp),
        record_rev=exp.rev,
        version_token=exp.version_token(),
        navigate_base=f"/record/{exp.id}",
        validate=lambda: _assistant_validate_dryrun(exp),
        search=lambda q: reader.search(q),
    )

    result = assistant_query.answer(classified, ctx, req.grounded_rev)
    # Read-only: rev is unchanged; echo the current validator for convenience.
    response.headers["ETag"] = exp.etag()
    return result


# --- 19b. assistant memory query (RECORD-AGNOSTIC, READ-ONLY, P34.4) -----------
#
# Cross-surface consistency: the Project Memory surface has NO record, so it uses
# this record-agnostic sibling of the record endpoint instead of the per-experiment
# path (which would 404 for a non-experiment id). A free-form question is classified
# with the SAME pure classifier; a project-memory question is answered purely from
# the memory reader (leads to verify, never a verdict), and ANY other question is an
# honest refusal directing the user to open a record. It has NO experiment path
# param, loads/creates NO record, mutates nothing, and inherits the app-wide auth.


@router.post(
    "/assistant/memory/query",
    tags=[TAG_ASSISTANT],
    summary="Ask Project Memory a Question",
    description=(
        "The record-agnostic counterpart of the per-record assistant operation, for "
        "surfaces that have no record open. The same fixed classifier is applied: a "
        "project-memory question is answered purely from the Project Memory reader "
        "as leads to verify, and any other question is refused honestly with a "
        "pointer to open a record first.\n\n"
        "There is no language model, no record is loaded or created, and nothing is "
        "mutated. It never states a pass, fail, valid, or invalid conclusion."
    ),
    response_description="The memory-scoped answer with its leads, or an honest refusal.",
    responses={
        **_R_UNAUTHORIZED,
        400: {
            "description": (
                "The question is blank or exceeds the character limit. Nothing was "
                "classified or answered."
            )
        },
    },
)
def post_assistant_memory_query(
    req: AssistantQueryRequest = Body(..., description=_ASSISTANT_BODY_DESCRIPTION),
):
    # Same typed guards as the record endpoint: empty/whitespace or oversized
    # questions are rejected with a stable typed error (never a 500).
    question = req.question if isinstance(req.question, str) else ""
    if not question.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "empty_question", "message": "A non-empty question is required."},
        )
    if len(question) > _ASSISTANT_MAX_QUESTION:
        return JSONResponse(
            status_code=400,
            content={
                "error": "question_too_long",
                "message": f"The question exceeds the {_ASSISTANT_MAX_QUESTION}-character limit.",
            },
        )
    # history is presentation-only; cap it and never let it influence grounding.
    _ = (req.history or [])[:_ASSISTANT_MAX_HISTORY]

    # No record is loaded or created — the memory reader is the only grounding.
    reader = memory.get_default_reader()
    classified = assistant_query.classify(question)
    return assistant_query.answer_memory_scope(classified, lambda q: reader.search(q))


# --- 20. about + api docs (Settings / Help, P36.4, READ-ONLY) ------------------
#
# Two GET-only, mutation-free routes backing the Settings page. Both reuse
# EXISTING authoritative sources (never a second copy of app identity or the
# API surface) and both live on THIS `/api`-prefixed router, so they are
# base-path-correct under {base}/api/* exactly like every other route here.


@router.get(
    "/about",
    tags=[TAG_META],
    summary="Get App and Provenance Metadata",
    description=(
        "Non-sensitive identity and provenance for this deployment: the app "
        "version, the build commit when the deployment supplies one (otherwise "
        "`null` — it is never guessed), the official ISAAC record-schema version "
        "this build validates against, the runtime data mode, the persistence "
        "model, the data regime, and the name of the deterministic core package.\n\n"
        "Every value is reused from the same authoritative source "
        "`GET /api/health` reads, so the two can never disagree. Read-only."
    ),
    response_description="The app version, build commit, schema version, runtime mode, and data regime.",
    responses={**_R_UNAUTHORIZED},
)
def about() -> dict:
    """MAINTAINER NOTE (not the published description — see ``description=`` above).

    Every field is reused from an existing authoritative source — `__version__`
    and `_build_commit()` (the SAME deploy-identity read `/health` uses),
    `EXPECTED_VERSION` from `isaac_records.official` (the vendored official
    schema's version, read-only import — that module is never modified here),
    and `runtime_mode.runtime_mode()` (the SAME fail-closed resolver `/health`
    uses). `persistence` and `data_regime` are fixed, non-configurable literals
    describing this prototype's current scope.

    The published `description=` states what the endpoint RETURNS; it deliberately
    does not enumerate what is withheld (hostnames, infrastructure internals,
    environment values, credentials, absolute paths), because an enumeration of
    withheld things reads as an inventory and is itself scanned by the
    ``/api/openapi`` leak guard in ``tests/test_about_and_openapi.py``.
    """
    return {
        "app_version": __version__,
        "build_commit": _build_commit(),
        "record_schema_version": EXPECTED_VERSION,
        "runtime_mode": runtime_mode.runtime_mode(),
        "persistence": "ephemeral",
        "data_regime": "synthetic-only",
        "core": "isaac_records",
    }


@router.get(
    "/openapi",
    tags=[TAG_META],
    summary="Get This API's OpenAPI Document",
    description=(
        "This application's own generated OpenAPI document — the same document "
        "served at the root `/openapi.json`, but reachable under the deployment's "
        "base path so a browser client can fetch it without knowing the root.\n\n"
        "It is generated from the live routes, never hand-maintained, so it cannot "
        "drift from what a caller can actually reach. It describes route signatures "
        "and documentation only: no runtime state and no configuration values. "
        "Read-only."
    ),
    response_description="The generated OpenAPI document for this application.",
    responses={**_R_UNAUTHORIZED},
)
def api_openapi(request: Request) -> dict:
    """The app's generated OpenAPI schema, reachable under the base-path-prefixed
    router (byte-identical to the root `/openapi.json` FastAPI already serves,
    just reachable at {base}/api/openapi so the Settings "API Documentation"
    card can fetch it correctly under a deployed base path). No hand-maintained
    duplicate description: `request.app.openapi()` is FastAPI's own generated
    schema, built from the SAME routes an authenticated user can already call —
    route signatures only, never secrets or runtime state.
    """
    return request.app.openapi()


# --- 21. schema & vocabulary browser (P36.6, READ-ONLY reference plane) --------
#
# A read-only browser over the CANONICAL official schema + vocabulary — NOT the
# portal Ontology system (no propose/review/approve/edit/role/persistence
# affordance exists anywhere for it). Every field, type, required flag, enum,
# description, and allOf relationship the frontend renders comes verbatim from
# these two sources: the vendored schema (loaded through
# ``official.schema_path(REPO_ROOT)`` — the SAME path resolver
# ``load_official_validator`` uses, never hardcoded here) and ``vocabulary/*.json``.
# Deterministic and side-effect-free: nothing is mutated, nothing is written.
# This route's body legitimately carries keys like ``schema``/``required`` — it
# is the reference/truth plane (the vendored PUBLIC schema), not the memory
# plane, so the memory-plane forbidden-key rule does not apply here.


@router.get(
    "/schema",
    tags=[TAG_SCHEMA],
    summary="Browse the Official Schema and Vocabularies",
    description=(
        "The vendored official ISAAC record schema verbatim, its title and the "
        "version this build validates against, plus every controlled vocabulary in "
        "the repository keyed by its filename stem.\n\n"
        "Every field, type, required flag, enumeration, description and composition "
        "relationship a client renders comes straight from these two sources; the "
        "schema is loaded through the same path resolver the validator uses, never "
        "a hardcoded copy. This is a read-only reference view of the public "
        "canonical schema — there is no propose, review, approve, or edit "
        "affordance."
    ),
    response_description="The official schema, its version, and the controlled vocabularies.",
    responses={**_R_UNAUTHORIZED},
)
def get_schema() -> dict:
    schema = json.loads(schema_path(REPO_ROOT).read_text(encoding="utf-8"))
    vocab_dir = REPO_ROOT / "vocabulary"
    vocabularies = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(vocab_dir.glob("*.json"))
    } if vocab_dir.is_dir() else {}
    return {
        "schema_title": schema.get("title"),
        "schema_version": EXPECTED_VERSION,
        "schema": schema,
        "vocabularies": vocabularies,
    }


# --- 22. read-only database reconnaissance (Slice 2A) --------------------------
#
# ONE operation, `GET /api/runtime/database/recon`, over the isolated app
# Postgres database described in `docs/postgres-test-db-guide.md`.
#
# Why it exists here and not in `scripts/`: the guide (lines 8-13) states the
# database is reachable ONLY from the deployed pod, and the Dockerfile COPY
# allowlist ships exactly one file out of `scripts/`. Deployment is therefore
# the delivery mechanism, so the shared logic lives in `isaac_api.db_recon` and
# this route is the supported entry point. `scripts/db_recon.py` remains an
# UNEXECUTED dev/design wrapper that is absent from the image.
#
# What it is NOT: it is not a record read path. The guide keeps hosted display
# of per-record content CLOSED BY DEFAULT pending an explicit visibility
# decision, and authorises aggregate output now. This operation therefore
# projects a FROZEN, strictly narrower key set than the reconnaissance report:
# no record id (not even a digest list), no title, no scientific value, no full
# JSON, no structural path list, no vocabulary values, no host, port, user,
# password, secret name, or connection string, and no driver text of any kind.
#
# LEAST PRIVILEGE AGAINST THE OWNER'S ENUMERATED LIST (gate G3).
# `docs/postgres-test-db-guide.md`, "Displaying record content", authorises a
# NAMED list and nothing wider: "record counts, counts by type and domain,
# validation totals, schema version, database reachability". Slice 2A shipped
# four aggregates that are not on it and that are derived by reading the stored
# documents themselves — `by_instance_path`, `distinct_structural_signatures`,
# `total_link_count`/`dangling_link_count` — plus `vocabulary_term_count`, a
# cardinality of production-derived vocabulary rows. They are withheld here.
#
# The rule that decides it: THE SCHEMA MAY DESCRIBE THE DATA; THE DATA MAY NOT
# DESCRIBE ITSELF. `by_rule_family` (validator keywords) and `by_schema_path`
# (pointers into the vendored PUBLIC schema) are produced by the schema and are
# retained as a breakdown of the authorised "validation totals". A path through
# a record INSTANCE, a count of distinct record SHAPES, and a count of
# `data->'links'` entries can only be produced by reading the stored documents,
# so they are per-record structure and stay closed until the owner says
# otherwise. The withheld names are still stated in the response, as fixed
# constants, so the narrowing is visible rather than silent.
#
# The full reconnaissance report still computes them: they are consumed only by
# `scripts/db_recon.py`, which the Dockerfile COPY allowlist deliberately keeps
# out of the image (only `scripts/check_graphify_freshness.py` is copied), so
# there is no application route by which they can be reached.
#
# It takes no query parameter, no body, no SQL, no record id, no schema path
# and no filter. There is nothing for a caller to steer.

#: Version of the SHAPE of this operation's response. Bump on a breaking change.
_DB_RECON_REPORT_FORMAT_VERSION = 1

#: The FROZEN top-level key allowlist. Every response this operation can return
#: — ok, not_configured, busy, refused, error — carries exactly these keys and
#: nothing else. The projection is built key-by-key from this tuple, so a field
#: cannot be added to the payload by accident somewhere downstream.
_DB_RECON_RESPONSE_KEYS: tuple[str, ...] = (
    "status",
    "report_format_version",
    "app_commit",
    "schema_version",
    "schema_fingerprint",
    "generated_at",
    "database",
    "dataset",
    "integrity",
    "limitations",
)

#: The FROZEN `dataset` key allowlist. Every one of these is either explicitly
#: enumerated by `docs/postgres-test-db-guide.md` ("record counts, counts by
#: type and domain, validation totals, schema version, database reachability"),
#: a breakdown of "validation totals" produced by the PUBLIC schema rather than
#: by the data, or a constant published in the guide itself.
#:
#: The block is built key-by-key FROM this tuple, so a record-derived aggregate
#: cannot re-appear by an edit somewhere downstream: an unlisted key raises, and
#: a missing one raises too.
_DB_RECON_DATASET_KEYS: tuple[str, ...] = (
    # record counts (enumerated)
    "total_records",
    "records_scanned",
    "records_parsed",
    "parse_failures",
    "record_id_digest_count",
    # the guide's own documented seed size, and the comparison against it
    "expected_seed_rows",
    "seed_count_matches",
    # validation totals (enumerated)
    "records_passing_full_schema",
    "records_failing_full_schema",
    "total_validation_issues",
    # breakdowns of those totals, produced by the schema, never by a value
    "by_rule_family",
    "by_schema_path",
    # counts by type and domain (enumerated)
    "by_record_type",
    "by_record_domain",
    # reachability of the vocabulary table — presence, not cardinality
    "vocabulary_cache_present",
    # what this projection deliberately does NOT carry, named in the response
    "withheld_pending_visibility_decision",
)

#: The FROZEN `integrity` key allowlist. Nothing here is derived from a record:
#: every field is an operational property of the scan itself.
_DB_RECON_INTEGRITY_KEYS: tuple[str, ...] = (
    "transaction_read_only",
    "rows_before",
    "rows_after",
    "rows_modified",
    "full_schema_fingerprint_match",
    "partial_schema_validation_runs",
    "schema_stable_across_run",
    "dml_statements_issued",
    "ddl_statements_issued",
    "read_statements_issued",
    "session_statements_issued",
)

#: Aggregates the reconnaissance report computes and this operation WITHHOLDS,
#: because the database owner's authorization does not name them and each is
#: derived by reading the stored documents. Fixed code constants — nothing is
#: interpolated, so this adds no leak surface. Naming them keeps the narrowing
#: auditable instead of invisible.
_DB_RECON_WITHHELD_AGGREGATES: tuple[str, ...] = (
    "by_instance_path",
    "distinct_structural_signatures",
    "total_link_count",
    "dangling_link_count",
    "vocabulary_term_count",
)

#: What the numbers above CANNOT establish, carried in every response.
#:
#: `db_recon.HONEST_NOTES` is scrupulous about the difference between a
#: tripwire and a guarantee, but it is not projected: the served report would
#: otherwise show a bare `gates: {not_production_shaped: true, tls: true}` from
#: which a reader would reasonably conclude the app VERIFIED it is not talking
#: to production. It cannot, and the code says so — so the caveats travel with
#: the numbers they qualify.
#:
#: This is a FIXED tuple of code constants. Nothing is interpolated, nothing is
#: derived from the database, the environment, or the report, so it adds no
#: leak surface: the strings are byte-identical on every call.
_DB_RECON_LIMITATIONS: tuple[str, ...] = (
    "The production-isolation gate is a TRIPWIRE, not proof. It refuses on row "
    "count, table owner and non-superuser status; a small production database "
    "owned by a similarly named non-superuser role would pass it. The real "
    # The role NAME is deliberately not spelled here: this string is carried
    # by the failure shapes too, and those must never echo a configured
    # connection value.
    "guarantee is external — this app's database role is granted no access to "
    "any other database on the cluster — and that grant cannot be verified "
    "from inside a connection.",
    # NB: the libpq parameter NAME is deliberately not spelled here. It is a
    # connection-string token, and this response must never contain one — the
    # endpoint's own tests forbid the substring, correctly.
    "TLS is confirmed encrypted server-side via pg_stat_ssl, but the default "
    "TLS mode ('require') encrypts WITHOUT verifying the server certificate. "
    "Encrypted is not the same as authenticated; authenticated TLS needs "
    "'verify-full' plus a CA bundle.",
    "server_version is a server-controlled string. It is emitted only when it "
    "matches a dotted-numeric shape and is replaced by a mask token otherwise; "
    "server_version_major is the parsed integer and carries the useful signal.",
    "No write is possible because the transaction is verified read-only "
    "server-side and every statement passes a SELECT-only allowlist before it "
    "is issued. rows_before/rows_after are compared as a CONCURRENCY CHECK, "
    "not as a mutation proof: a row-count equality cannot detect an UPDATE and "
    "cannot distinguish this scan's writes from a concurrent writer's. "
    "rows_modified is therefore any writer's net delta over the scan window, "
    "and is 0 by construction because an unequal count refuses the run before "
    "a report is produced.",
    "The statement counters observe every statement this service issues "
    "through a cursor. They are not a wire-level record: the driver's own "
    "transaction framing never passes through a cursor and is not counted.",
    "This operation returns AGGREGATES ONLY. Hosted display of per-record "
    "content is closed by default pending an explicit visibility decision, so "
    "no record id, title, scientific value or stored document is reachable "
    "here.",
    "Narrower than aggregates-in-general: the owner's authorization names "
    "record counts, counts by type and domain, validation totals, schema "
    "version and reachability. Aggregates outside that list which are derived "
    "by reading the stored documents — paths through a record instance, a "
    "count of distinct record shapes, link counts, and the vocabulary row "
    "count — are withheld pending an explicit visibility decision, and are "
    "named in dataset.withheld_pending_visibility_decision. The retained "
    "breakdowns (by_rule_family, by_schema_path) are produced by the vendored "
    "public schema, not by any stored value.",
)

#: The guide's documented classification of this database.
_DB_RECON_CLASSIFICATION = "isolated-app-postgres"
#: Hosted per-record display is closed by default (guide, "Displaying record
#: content") until an explicit visibility decision is made.
_DB_RECON_RECORD_DISPLAY = "closed"
#: Documented seed size: "the 30 earliest real records from production".
_DB_RECON_EXPECTED_SEED_ROWS = db_recon.DOCUMENTED_SEED_ROWS

#: A repeat call inside this window is served from memory, so hammering the
#: endpoint cannot hammer the database.
_DB_RECON_CACHE_TTL_SECONDS = 60.0

#: Fetch bound. One more than the production-shape refusal threshold, so any
#: table this operation is willing to look at is scanned whole — the validation
#: totals then cover every row rather than a page of them — while a
#: surprise-huge table is refused by the gate before it is ever paged in.
#: (It also used to be what made `dangling_link_count` a fact rather than an
#: approximation; that aggregate is no longer projected — see G3 above.)
_DB_RECON_MAX_RECORDS = db_recon.MAX_PLAUSIBLE_RECORD_ROWS + 1

#: Per-process salt for the record_id digests the recon computes internally.
#: The digests are NOT projected into the response (only their count is), so
#: this exists purely so no stable identifier-derived value is ever formed.
_DB_RECON_SALT = hashlib.sha256(os.urandom(32)).hexdigest()

#: Held NON-BLOCKING for the duration of a scan. At most one scan — and
#: therefore at most ONE connection from this operation — exists at a time, so
#: the role's connection limit of 5 cannot be approached from here even though
#: sync endpoints run in a threadpool.
_DB_RECON_SCAN_LOCK = threading.Lock()

#: Guards the small mutable cache below.
_DB_RECON_STATE_LOCK = threading.Lock()
#: The last SUCCESSFUL projected payload, and the monotonic time it was made.
_db_recon_cached_payload: dict | None = None
_db_recon_cached_at: float | None = None
#: `{status, at}` for the last scan of ANY outcome, surfaced by `/health`.
_db_recon_last: dict | None = None


def _db_recon_configured(env: Mapping[str, str] | None = None) -> bool:
    """The guide's documented feature switch: `PGHOST` present. Reads env only."""
    source = os.environ if env is None else env
    return bool((source.get("PGHOST") or "").strip())


def _db_recon_envelope(
    *,
    status: str,
    database: dict,
    dataset: dict | None = None,
    integrity: dict | None = None,
    schema_version: str | None = None,
    schema_fingerprint: str | None = None,
) -> dict:
    """Build a response from the FROZEN key allowlist. Nothing else can get in."""
    built = {
        "status": status,
        "report_format_version": _DB_RECON_REPORT_FORMAT_VERSION,
        "app_commit": _build_commit(),
        "schema_version": schema_version,
        "schema_fingerprint": schema_fingerprint,
        "generated_at": _now_iso(),
        "database": database,
        "dataset": dataset,
        "integrity": integrity,
        # Constant, in EVERY shape, so the key set stays frozen and uniform.
        "limitations": list(_DB_RECON_LIMITATIONS),
    }
    return {key: built[key] for key in _DB_RECON_RESPONSE_KEYS}


#: The FROZEN `database` key allowlist. Nothing here is derived from a record:
#: every value is a code-level constant, a boolean, a masked version string, or
#: a gate/exception NAME. It is frozen anyway, for the reason G3 exists — the
#: `dataset` leak happened because only the TOP-LEVEL keys were frozen, so a
#: record-derived value could be added to a nested block without tripping a
#: single contract test. Two of the three nested blocks were closed by the G3
#: narrowing; this closes the third, so the structural gap is gone rather than
#: merely relocated.
_DB_RECON_DATABASE_KEYS: tuple[str, ...] = (
    "configured",
    "classification",
    "contains_production_derived_records",
    "record_display",
    "server_version",
    "server_version_major",
    "expected_major_version",
    "expected_major_version_match",
    "gates",
    "refusal_gate",
    "refusal_class",
)

#: The FROZEN gate-name allowlist for `database.gates`. Gate names are code
#: constants, so this is belt-and-braces — but an unlisted gate name reaching
#: the response is exactly the shape of mistake that must fail closed.
_DB_RECON_GATE_KEYS: tuple[str, ...] = (
    "database_identity",
    "current_user",
    "session_user",
    "tls",
    "records_table_present",
    "transaction_read_only",
    "not_production_shaped",
)


def _db_recon_database_block(
    *,
    configured: bool,
    server_version: str | None = None,
    server_version_major: int | None = None,
    expected_major_version_match: bool | None = None,
    gates: dict | None = None,
    refusal_gate: str | None = None,
    refusal_class: str | None = None,
    strict: bool = False,
) -> dict:
    """The `database` sub-object. NEVER carries host, port, user, or password.

    Always PROJECTED through `_DB_RECON_DATABASE_KEYS` / `_DB_RECON_GATE_KEYS`,
    so an unlisted key can never be served regardless of `strict`: a projection
    onto a fixed allowlist cannot invent a key.

    `strict` additionally RAISES when the builder produced a key the allowlist
    does not have — a developer-error detector, so a new field cannot be added
    and silently dropped. It is set on the success path only, and deliberately
    NOT on the failure envelopes: those are what a raise degrades INTO, so if
    they raised too, a broken allowlist would escape as an unhandled 500 with a
    traceback instead of the sanitized envelope. Fail-closed has to include the
    closing.
    """
    built = {
        "configured": configured,
        "classification": _DB_RECON_CLASSIFICATION if configured else None,
        # The guide is explicit that the seeded rows are real
        # production-derived records, so this is stated, not inferred.
        "contains_production_derived_records": True if configured else None,
        "record_display": _DB_RECON_RECORD_DISPLAY,
        "server_version": server_version,
        "server_version_major": server_version_major,
        "expected_major_version": db_recon.EXPECTED_SERVER_MAJOR_VERSION,
        # Reported, NEVER gated: a cluster upgrade must not break this route.
        "expected_major_version_match": expected_major_version_match,
        "gates": gates if gates is not None else {key: None for key in _DB_RECON_GATE_KEYS},
        # A gate name and an exception CLASS name are code-level constants, so
        # they are safe to name. No driver message, ever.
        "refusal_gate": refusal_gate,
        "refusal_class": refusal_class,
    }
    built_gates = built["gates"] or {}
    if strict:
        if set(built) - set(_DB_RECON_DATABASE_KEYS):
            raise KeyError("db_recon database key not on the frozen allowlist")
        if set(built_gates) - set(_DB_RECON_GATE_KEYS):
            raise KeyError("db_recon gate key not on the frozen allowlist")
    block = {key: built.get(key) for key in _DB_RECON_DATABASE_KEYS}
    if "gates" in _DB_RECON_DATABASE_KEYS:
        block["gates"] = {key: built_gates.get(key) for key in _DB_RECON_GATE_KEYS}
    return block


def _db_recon_leak_guard(payload: dict, env: Mapping[str, str]) -> dict:
    """The last line of defence, run over EVERY serialised response shape.

    The success path always ran this. The `not_configured`, `refused`, `error`
    and `busy` shapes did not, so the guarantee had a gap: they are safe by
    construction today — every string in them is a code constant — but "last
    line of defence" is worth nothing if it is conditional on the outcome. It
    is now unconditional.

    A tripped scan, or a payload that will not even serialise, collapses to a
    directly-built sanitized envelope. That envelope is NOT re-scanned, which
    is what keeps this from recursing.
    """
    try:
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        issues = db_recon.scan_for_leaks(
            serialized,
            env=env,
            allow_raw_ids=False,
            leaves=db_recon.string_leaves(payload),
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:  # noqa: BLE001 - the guard must never leak
        _log.info("db_recon outcome=error gate=leak_scan type=%s", type(exc).__name__)
        return _db_recon_envelope(
            status="error",
            database=_db_recon_database_block(
                configured=True,
                refusal_gate="leak_scan",
                refusal_class=type(exc).__name__,
            ),
        )
    if issues:
        _log.info("db_recon outcome=refused gate=leak_scan codes=%s", ",".join(issues))
        return _db_recon_envelope(
            status="error",
            database=_db_recon_database_block(
                configured=True, refusal_gate="leak_scan", refusal_class=None
            ),
        )
    return payload


def _db_recon_not_configured(env: Mapping[str, str]) -> dict:
    """No `PGHOST`: preserve today's no-database behaviour. Opens nothing."""
    return _db_recon_leak_guard(
        _db_recon_envelope(
            status="not_configured",
            database=_db_recon_database_block(configured=False),
        ),
        env,
    )


def _db_recon_failure(
    *,
    env: Mapping[str, str],
    status: str,
    gate: str | None,
    exception_class: str | None,
) -> dict:
    """A sanitized refusal/error. Carries a gate name and a class name only."""
    return _db_recon_leak_guard(
        _db_recon_envelope(
            status=status,
            database=_db_recon_database_block(
                configured=True, refusal_gate=gate, refusal_class=exception_class
            ),
        ),
        env,
    )


def _db_recon_project(report: Mapping, authority: Mapping, statements: Mapping) -> dict:
    """Project the reconnaissance report onto the FROZEN response allowlist.

    Strictly narrower than the report. Deliberately EXCLUDED, and asserted so by
    `apps/api/tests/test_db_recon_endpoint.py`:

    * `structure.distinct_signatures[].paths` — the full structural path lists;
    * `structure.distinct_signature_count` — even the COUNT of distinct record
      shapes, which is a record-derived structural fact the owner did not
      enumerate (G3);
    * `records.record_id_digests.digests` — only its count survives;
    * raw record ids under any flag (the endpoint never sets one);
    * `validation.failing_instance_paths` — paths through a record INSTANCE.
      Every segment is masked against the public schema, but the fact that a
      path is populated is produced by reading the stored document (G3);
    * `records.links.*` — `total_link_count` and `dangling_link_count` are
      derived from `data->'links'` (G3). The guide mentions dangling links
      under "Gotchas to code around", which is an instruction for CODE, not an
      authorization to DISPLAY;
    * `vocabulary_cache` grouped VALUES — because the module's own notes
      concede a lowercase slug cannot be PROVEN to be a vocabulary term rather
      than data — and its ROW COUNT too, which is a cardinality of
      production-derived rows and is not on the owner's enumerated list. Only
      presence survives.
    """
    connection = report.get("connection") or {}
    gate_states = report.get("gates") or {}
    records = report.get("records") or {}
    validation = report.get("validation") or {}
    mutation = report.get("mutation_check") or {}

    analyzed = int(records.get("analyzed") or 0)
    parse_failures = int(records.get("unreadable_payloads") or 0)
    total = int(records.get("total") or 0)
    families = list(validation.get("failure_rule_families") or [])

    gates = {
        "database_identity": gate_states.get("current_database") == "pass",
        "current_user": gate_states.get("current_user") == "pass",
        # `check_current_user` refuses a SET ROLE, so a pass IS the proof; this
        # re-states the observation rather than assuming it.
        "session_user": str(connection.get("session_user") or "")
        == db_recon.EXPECTED_ROLE,
        "tls": gate_states.get("tls") == "pass",
        "records_table_present": gate_states.get("records_table") == "pass",
        "transaction_read_only": gate_states.get("transaction_read_only") == "pass",
        "not_production_shaped": gate_states.get("not_production_shaped") == "pass",
    }

    built_dataset = {
        "total_records": total,
        "expected_seed_rows": _DB_RECON_EXPECTED_SEED_ROWS,
        "seed_count_matches": total == _DB_RECON_EXPECTED_SEED_ROWS,
        "records_scanned": analyzed,
        "records_parsed": analyzed - parse_failures,
        "parse_failures": parse_failures,
        "records_passing_full_schema": int(validation.get("passed") or 0),
        "records_failing_full_schema": int(validation.get("failed") or 0),
        "total_validation_issues": sum(int(f.get("error_count") or 0) for f in families),
        "by_rule_family": [
            {
                "family": str(f.get("family")),
                "records_affected": int(f.get("records_affected") or 0),
                "error_count": int(f.get("error_count") or 0),
            }
            for f in families
        ],
        # Pointers into the vendored PUBLIC schema, masked by `db_recon` before
        # they get here: a segment survives only if the public schema already
        # publishes that name. The schema describes the data; this is the
        # schema side of that line, so it is retained. The INSTANCE-path
        # counterpart is not — see the docstring and G3.
        "by_schema_path": [
            {
                "schema_path": str(p.get("schema_path")),
                "error_count": int(p.get("error_count") or 0),
            }
            for p in (validation.get("failing_schema_paths") or [])
        ],
        "by_record_type": list(records.get("by_record_type") or []),
        "by_record_domain": list(records.get("by_record_domain") or []),
        "record_id_digest_count": int(
            (records.get("record_id_digests") or {}).get("count") or 0
        ),
        # Reachability of the table, not the size of its contents.
        "vocabulary_cache_present": bool(
            (report.get("vocabulary_cache") or {}).get("present")
        ),
        "withheld_pending_visibility_decision": list(_DB_RECON_WITHHELD_AGGREGATES),
    }
    # Built FROM the frozen allowlist: an unlisted key cannot ride along, and a
    # dropped one raises here rather than silently vanishing from the contract.
    dataset = {key: built_dataset[key] for key in _DB_RECON_DATASET_KEYS}
    extra = set(built_dataset) - set(_DB_RECON_DATASET_KEYS)
    if extra:
        raise KeyError("dataset key not on the frozen allowlist")

    rows_before = int(mutation.get("records_before") or 0)
    rows_after = int(mutation.get("records_after") or 0)
    counts = dict(statements or {})
    built_integrity = {
        "transaction_read_only": connection.get("transaction_read_only") == "on",
        "rows_before": rows_before,
        "rows_after": rows_after,
        # ANY writer's net delta over the scan window, not necessarily ours —
        # a row-count comparison cannot attribute a change. It is 0 by
        # construction: `run_recon` raises `MutationDetected` on an unequal
        # count, so no report reaches this projection with a non-zero delta.
        "rows_modified": rows_after - rows_before,
        "full_schema_fingerprint_match": bool(authority.get("stable")),
        # A literal COUNT, as the name says: the number of validations run
        # against a schema that was not the full vendored schema. It is always
        # 0 because a partial schema refuses at the `full_schema_authority`
        # gate in `_db_recon_scan`, before a single record is validated. The
        # before/after fingerprint signal it used to smuggle now has its own
        # boolean below, so neither field lies about its type.
        "partial_schema_validation_runs": 0,
        "schema_stable_across_run": bool(authority.get("stable")),
        # OBSERVED from a statement-auditing proxy around the connection, not
        # asserted about ourselves.
        "dml_statements_issued": int(counts.get("dml", 0)),
        "ddl_statements_issued": int(counts.get("ddl", 0)),
        "read_statements_issued": int(counts.get("read", 0)),
        "session_statements_issued": int(counts.get("session", 0)),
    }
    integrity = {key: built_integrity[key] for key in _DB_RECON_INTEGRITY_KEYS}
    if set(built_integrity) - set(_DB_RECON_INTEGRITY_KEYS):
        raise KeyError("integrity key not on the frozen allowlist")

    return _db_recon_envelope(
        status="ok",
        schema_version=EXPECTED_VERSION,
        schema_fingerprint=str(authority.get("fingerprint") or ""),
        database=_db_recon_database_block(
            configured=True,
            # `server_version` is a SERVER-CONTROLLED string: a 100,000-char
            # value, or `18.0 (SUPER-SECRET) /etc/passwd`, would otherwise be
            # projected verbatim and the leak scan cannot recognise arbitrary
            # text. Masked through the same dotted-numeric guard the module
            # already applies to `isaac_record_version`; anything else becomes
            # `<unrecognized>`. Nothing that matters is lost —
            # `server_version_major` is an int and carries the useful signal.
            server_version=db_recon.safe_version_value(
                connection.get("server_version")
            ),
            server_version_major=connection.get("server_version_major"),
            expected_major_version_match=connection.get("expected_major_version_match"),
            gates=gates,
            # Success path only — see the docstring: the failure envelopes this
            # would degrade into must NOT raise, or fail-closed stops closing.
            strict=True,
        ),
        dataset=dataset,
        integrity=integrity,
    )


def _db_recon_scan(env: Mapping[str, str]) -> dict:
    """Open exactly ONE connection, run the recon, project, leak-scan, close.

    Every exit path closes the cursor (inside `run_recon`) and the connection
    (in the `finally` here), rolls back first, and returns a sanitized payload.
    No driver exception, traceback, connection string, host, port, user or
    password can escape: only an exception CLASS name and a fixed reason,
    mirroring the CLI's `BaseException` handler.

    ORDER MATTERS: the socket-free environment gates run BEFORE
    `connect_psycopg2`, so `db_recon`'s own contract ("the env gates run before
    any socket is opened") holds for this entry point too. It previously held
    only for the CLI: the endpoint connected first and reached `check_env_gates`
    inside `run_recon`, so a wrong `PGDATABASE` burned one of the role's five
    connections before refusing.
    """
    before = db_recon.schema_authority(REPO_ROOT)
    if not before.get("full_schema"):
        # A trimmed or partial schema must never act as validator authority: it
        # would report a false "everything passes" over real records.
        _log.info("db_recon outcome=refused gate=full_schema_authority")
        return _db_recon_failure(
            env=env,
            status="refused",
            gate="full_schema_authority",
            exception_class=None,
        )

    try:
        # Socket-free gates first. `run_recon` runs them again (defence in
        # depth); `check_env_gates` is pure and idempotent, so running it twice
        # is free and removing either call would weaken the other entry point.
        db_recon.check_env_gates(env, require_opt_in=False)
    except db_recon.ReconRefusal as exc:
        _log.info("db_recon outcome=refused gate=%s connected=no", exc.gate)
        return _db_recon_failure(
            env=env,
            status="refused",
            gate=exc.gate,
            exception_class=type(exc).__name__,
        )

    connection = None
    audited = None
    try:
        connection = db_recon.connect_psycopg2(env)
        audited = db_recon.AuditedConnection(connection)
        report = db_recon.run_recon(
            audited,
            env=env,
            salt=_DB_RECON_SALT,
            root=REPO_ROOT,
            max_records=_DB_RECON_MAX_RECORDS,
            emit_raw_record_ids=False,
            require_opt_in=False,
        )
    except db_recon.ReconRefusal as exc:
        _log.info("db_recon outcome=refused gate=%s", exc.gate)
        return _db_recon_failure(
            env=env,
            status="refused",
            gate=exc.gate,
            exception_class=type(exc).__name__,
        )
    except (KeyboardInterrupt, SystemExit):
        # Process-lifecycle signals are not scan outcomes. Converting them into
        # a 200 `status: "error"` would swallow a shutdown or a Ctrl-C.
        raise
    except BaseException as exc:  # noqa: BLE001 - see docstring
        _log.info("db_recon outcome=error type=%s", type(exc).__name__)
        return _db_recon_failure(
            env=env, status="error", gate=None, exception_class=type(exc).__name__
        )
    finally:
        if connection is not None:
            for method in ("rollback", "close"):
                fn = getattr(connection, method, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:  # noqa: BLE001 - cleanup must never raise
                        pass

    # Re-read the vendored schema AFTER validating: proves the authority the
    # records were judged against did not change under us mid-scan.
    after = db_recon.schema_authority(REPO_ROOT)
    authority = {
        "fingerprint": before.get("fingerprint"),
        "stable": bool(
            after.get("full_schema") and after.get("fingerprint") == before.get("fingerprint")
        ),
    }
    statements = audited.audit.as_dict() if audited is not None else {}

    # The serialisation lives INSIDE the guard with the projection it feeds: a
    # value the projection produced but `json.dumps` cannot encode would
    # otherwise escape as a bare 500 instead of this sanitized envelope.
    #
    # `string_leaves` IS COMPUTED HERE, INSIDE THE GUARD, FOR THAT SAME REASON —
    # and it is a distinct risk rather than the same one twice. `json.dumps`
    # encodes in C; `string_leaves` is a Python-level recursive walk, so it
    # exhausts the interpreter's stack at a shallower depth than the encoder
    # does. Measured: at depth 1500 `json.dumps` succeeds and `string_leaves`
    # raises `RecursionError`. Left below the `try`, that band would escape as a
    # bare 500 with a traceback — exactly what the paragraph above says this
    # design exists to prevent, reintroduced by the line added to close a
    # different hole. Not reachable through `_db_recon_project`, which projects
    # onto frozen allowlists and yields a payload about three levels deep; this
    # is defence in depth, and it costs one line.
    try:
        payload = _db_recon_project(report, authority, statements)
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        leaves = db_recon.string_leaves(payload)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:  # noqa: BLE001 - projection must never leak
        # `gate` names the STAGE, and three stages now live in this block. A
        # `RecursionError` from the leaf walk was previously attributed to
        # "projection", which is a safe response carrying a wrong label — and a
        # wrong label on a refusal is what a later reader debugs against.
        # Narrowed by exception type rather than by splitting the try, because
        # splitting it is what put the leaf walk outside a guard in the first
        # place.
        gate = "leaf_walk" if isinstance(exc, RecursionError) else "projection"
        _log.info("db_recon outcome=error gate=%s type=%s", gate, type(exc).__name__)
        return _db_recon_failure(
            env=env,
            status="error",
            gate=gate,
            exception_class=type(exc).__name__,
        )

    # Final backstop over the response, before it is returned. Both the
    # serialised text AND the payload's decoded string leaves — a value
    # containing a JSON-escaped character is invisible in the former.
    issues = db_recon.scan_for_leaks(
        serialized,
        env=env,
        allow_raw_ids=False,
        leaves=leaves,
    )
    if issues:
        _log.info("db_recon outcome=refused gate=leak_scan codes=%s", ",".join(issues))
        return _db_recon_failure(
            env=env, status="error", gate="leak_scan", exception_class=None
        )

    _log.info(
        "db_recon outcome=ok records=%d scanned=%d passed=%d failed=%d dml=%d ddl=%d",
        payload["dataset"]["total_records"],
        payload["dataset"]["records_scanned"],
        payload["dataset"]["records_passing_full_schema"],
        payload["dataset"]["records_failing_full_schema"],
        payload["integrity"]["dml_statements_issued"],
        payload["integrity"]["ddl_statements_issued"],
    )
    return payload


def _db_recon_cache_get() -> dict | None:
    """The cached successful payload while it is inside the TTL, else None."""
    with _DB_RECON_STATE_LOCK:
        if _db_recon_cached_payload is None or _db_recon_cached_at is None:
            return None
        if (time.monotonic() - _db_recon_cached_at) > _DB_RECON_CACHE_TTL_SECONDS:
            return None
        return copy.deepcopy(_db_recon_cached_payload)


def _db_recon_cache_put(payload: Mapping) -> None:
    """Record the outcome; cache the payload only when the scan succeeded."""
    global _db_recon_cached_payload, _db_recon_cached_at, _db_recon_last
    with _DB_RECON_STATE_LOCK:
        _db_recon_last = {"status": payload.get("status"), "at": payload.get("generated_at")}
        if payload.get("status") == "ok":
            _db_recon_cached_payload = copy.deepcopy(dict(payload))
            _db_recon_cached_at = time.monotonic()


def _db_recon_last_summary() -> dict | None:
    """`{status, at}` for the last scan in THIS process, or None. Zero I/O."""
    with _DB_RECON_STATE_LOCK:
        return dict(_db_recon_last) if _db_recon_last is not None else None


@router.get(
    "/runtime/database/recon",
    tags=[TAG_META],
    summary="Report Read-Only Reconnaissance of the App Database",
    description=(
        "A sanitized, aggregate-only reconnaissance report over this "
        "deployment's own application database. It answers one question — do "
        "the stored records validate against the vendored official ISAAC "
        "schema — and reports the answer as counts.\n\n"
        "The scan is strictly read-only, and no write is possible: the "
        "transaction is set AND verified read-only server-side, every "
        "statement is checked against a SELECT-only allowlist before it is "
        "issued, and values are always bound as parameters. The row count is "
        "also compared before and after, but that is a concurrency check "
        "rather than a mutation proof — a row-count equality cannot detect an "
        "update and cannot distinguish this scan's writes from a concurrent "
        "writer's, so it is the verified read-only transaction and the "
        "allowlist that carry the guarantee. The statement counters report "
        "every statement this service issues through a cursor; they are not a "
        "wire-level record, because the driver's own transaction framing never "
        "passes through one.\n\n"
        "The response carries aggregates only: record totals, counts by type "
        "and domain, validation totals by rule family and by schema path, and "
        "the gate results. It never carries a record id, a title, a scientific "
        "value, a stored document, a connection detail, or a credential; "
        "per-record content stays closed. A serialized-output scan runs over "
        "every response shape before it is returned and replaces it with a "
        "sanitized failure if it trips. Every shape also carries a fixed "
        "`limitations` list saying what the gates cannot establish — in "
        "particular that the production-isolation gate is a tripwire rather "
        "than proof, and that the confirmed transport encryption does not "
        "verify the server certificate.\n\n"
        "When the deployment has no database configured, the operation reports "
        "that and connects to nothing. Repeat calls inside a short window are "
        "served from memory, and a scan already in progress is reported as a "
        "conflict rather than opening a second connection. The operation takes "
        "no parameters and no body."
    ),
    response_description=(
        "The sanitized aggregate reconnaissance report, or a sanitized "
        "not-configured, refusal, or error report in the same shape."
    ),
    responses={
        **_R_UNAUTHORIZED,
        409: {
            "description": (
                "A reconnaissance scan is already running in this process. "
                "Nothing was connected to and nothing was read."
            )
        },
    },
)
def get_database_recon(response: Response) -> dict:
    env = os.environ
    if not _db_recon_configured(env):
        _log.info("db_recon outcome=not_configured")
        return _db_recon_not_configured(env)

    cached = _db_recon_cache_get()
    if cached is not None:
        _log.info("db_recon outcome=cache_hit")
        return cached

    # NON-BLOCKING: a second caller is told the truth immediately rather than
    # queueing behind a database round trip (and never opens a connection).
    if not _DB_RECON_SCAN_LOCK.acquire(blocking=False):
        _log.info("db_recon outcome=busy")
        response.status_code = 409
        return _db_recon_failure(
            env=env, status="busy", gate="concurrent_scan", exception_class=None
        )
    try:
        payload = _db_recon_scan(env)
    finally:
        _DB_RECON_SCAN_LOCK.release()

    _db_recon_cache_put(payload)
    return payload


# ---------------------------------------------------------------------------
# Record Verification
# ---------------------------------------------------------------------------
# Serves the sanitized aggregate report described in `verification.py`. Read
# only: no write, no lock on the workspace, no truth-path call beyond the
# validator's own read.
#
# The sweep costs ~19s over ten records, so it NEVER runs inside a request.
# `VerificationState` starts it on a background thread and answers `running`
# until a result exists. A request that blocked for 19s would time out behind
# the ingress and look like an outage.

def _verification_provider_factory() -> db_provider.DatastoreRecordProvider:
    """Build the datastore provider for the authorized private mode.

    CALLED ONLY when a caller asks for `authorized_private_sample`, and only from
    `VerificationState._work` on its background thread. The public mode never
    reaches this function, so the ordinary Statistics read still opens nothing.

    Passing this factory is the ONLY thing that makes the private mode reachable.
    Until it existed, `VerificationState` was constructed without one and the
    private mode could not obtain records at all -- "fail-closed by construction
    rather than by policy", as that class still documents. That construction was
    the right default while the capability was unauthorized; Q19 authorized it on
    2026-08-05 (`docs/evidence/2026-08-05-q19-q20-authorization.md`), so the
    factory is supplied and the remaining gates are the ones Dean actually
    specified rather than the absence of a wire.

    Nothing here relaxes a gate. Every constraint still lives in the provider:
    `db_recon.check_env_gates` pins `PGDATABASE`, and a wrong or absent value
    **refuses** before anything is opened; a missing `PGHOST`/`PGUSER`/
    `PGPASSWORD` is a different failure and produces **`unavailable`** from the
    connect gate, as does an image whose driver will not import (it is imported
    lazily, so it reports rather than raising); the transaction declares
    read-only twice and verifies it server-side; and the report is
    aggregate-only. This function adds no argument a caller can influence -- it
    reads `os.environ` and nothing else, so there is no request-derived value
    anywhere on this path.

    THE TWO FAILURE WORDS ARE NOT INTERCHANGEABLE, and an earlier version of
    this docstring said a missing `PGHOST` "refuses", which is false: only the
    `PGDATABASE` pin yields `refused`. Both are measured, per environment, in
    `apps/api/tests/test_verification_route_wiring.py`.

    Constructing the provider is itself side-effect free: with an empty
    environment it returns an object in state `not_run` rather than raising, and
    no socket is opened until `records()` is drained.
    """
    return db_provider.DatastoreRecordProvider(os.environ)


_VERIFICATION_STATE = verification.VerificationState(
    REPO_ROOT, provider_factory=_verification_provider_factory
)


@router.get(
    "/runtime/verification",
    tags=[TAG_VALIDATION],
    summary="Read the Record Verification Aggregate Report",
    description=(
        "Aggregate results of three programs run over a corpus of official "
        "ISAAC records: official schema validation, a stricter format-aware "
        "shadow validation, and a deterministic mutation harness that "
        "deep-clones each record before mutating it. **Which** corpus is "
        "selected by `mode`, and a completed report names it in "
        "`metadata.verification_mode`.\n\n"
        "Aggregate only. No record id, title, field value, evidence entry or "
        "per-record outcome appears, and every histogram is projected through a "
        "minimum-cell-size floor so a category with few occurrences is withheld "
        "rather than named.\n\n"
        "**Two corpora, selected by `mode`. A completed report names the one it "
        "read; a status envelope (`running`, `refused`, `unavailable`, `error`) "
        "carries no `metadata` at all, so it names no corpus and reports no "
        "figures.**\n\n"
        "* `public_reference` (default) — the ten public upstream ISAAC example "
        "records vendored in this repository. Already published, so reading them "
        "needs no approval, and a run in `public_reference` mode does not open a "
        "database connection to reach them.\n"
        "* `authorized_private_sample` — a bounded, read-only, aggregate-only "
        "pass over the records this application holds in its own datastore, "
        "under the approval recorded on 2026-08-05. This mode **does** open one "
        "short-lived read-only connection — to whatever host the process's own "
        "libpq environment names, which in the deployed configuration is the "
        "in-cluster database reached from the pod. Nothing on this path checks "
        "where the process is running; that it runs in the pod is how the "
        "deployment is configured, not something this operation enforces. Each "
        "record is deep-copied in memory, mutated only as a copy, and discarded; "
        "no identifier, title, field value, evidence entry or per-record outcome "
        "is retained or returned.\n\n"
        # The credential variable is described rather than named: `PGPASSWORD`
        # contains "password", and `test_about_and_openapi.py` scans the whole
        # generated document for that substring with no exception list. Spelling
        # it out fails that scan -- MEASURED, it did. The variable's real name is
        # in `_verification_provider_factory`'s docstring and in `db_provider`,
        # neither of which is published.
        "An unknown mode is **refused**, never silently served the other one. "
        "For the private mode the two failure words are not interchangeable, and "
        "each has its own cause. `refused` means an environment gate rejected "
        "the run before anything was opened — in practice that `PGDATABASE` is "
        "not exactly the expected database name, and absent counts as not "
        "exactly. `unavailable` means that gate passed but no connection was "
        "obtained: the driver would not import, or one of the remaining libpq "
        "connection variables (`PGHOST`, `PGUSER`, or the credential variable "
        "beside them) is missing or empty, or the attempt itself failed. So a "
        "deployment with `PGDATABASE` set and `PGHOST` unset reports "
        "`unavailable`, not `refused`.\n\n"
        "The sweep runs off the request path. The first call returns `running`; "
        "poll until `status` is `ok`."
    ),
    response_description="The sanitized aggregate report, or a status envelope.",
    responses={**_R_UNAUTHORIZED},
)
def get_runtime_verification(
    mode: str | None = Query(
        None,
        description=(
            "Which corpus to report on. Omit for the public reference preflight. "
            "A mode this build does not offer is refused, not substituted."
        ),
    ),
) -> dict:
    try:
        # The raw string is handed straight to `VerificationState.get`, which
        # checks it against its own closed mode tuple and answers `refused` for
        # anything else. Deliberately NOT validated with an Enum here: the tuple
        # is DERIVED from the authorization flags, so an Enum in the signature
        # would be a second, independently-maintained copy of the mode list that
        # could drift out of agreement with the thing that actually authorizes.
        return _VERIFICATION_STATE.get(mode)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:  # noqa: BLE001 - must never leak, must never 500
        # The exception text is not captured: it could carry a filesystem path
        # or a record value. `error` is all a caller may safely learn.
        return verification.build_pending_report("error")
