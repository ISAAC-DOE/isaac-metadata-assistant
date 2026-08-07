"""HTTP endpoints for the local UI prototype (all JSON, prefixed ``/api``).

Every verdict is produced by an ``isaac_records`` core function — this module only
routes, serializes (via ``serialize``), and enforces the synthetic-only governance
boundary. It adds no validation logic and never mutates the truth path.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Annotated, Literal, Mapping

import logging

from fastapi import APIRouter, Body, Depends, Header, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from isaac_records.audit import audit_records, render_audit
from isaac_records.complete import apply_answers, apply_corrections
from isaac_records.draft_validator import validate_draft
from isaac_records.export import export_draft
from isaac_records.extract.draft_builder import build_draft
from isaac_records.official import EXPECTED_VERSION, schema_path, validate_official
from isaac_records.portal_warnings import portal_warnings

from . import __version__
from . import assistant_query
from . import csv_ingest
from . import db_recon
from . import dependencies
from . import evidence_classify
from . import memory
from . import memory_graph
from . import runtime_mode
from . import runtime_records
from . import search
from . import serialize
from . import sources
from . import version_contract as vc
from . import workspace as ws
from .workflow import derive_workflow
from .workspace import REPO_ROOT, Experiment, atomic_write_text

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
            "and previews of the reference source files the evidence cites. "
            "Read-only."
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
            # (``workspace.py:608``), then ``exp.save()`` into ``scope_root(None)``. The
            # sentence above survives for a DIFFERENT and stronger reason: this build
            # exposes no record-creation surface at all. There is no ``POST
            # /api/experiments``, and ``create_experiment`` has no caller anywhere under
            # ``apps/api/isaac_api/`` — pinned by
            # ``test_tutorial_scope.py::test_create_experiment_has_no_caller_in_the_api_package``,
            # so a future route that took a client-supplied id could not be added
            # silently. ("Requires a session_id"
            # was the earlier justification and it was too weak to carry the sentence:
            # ``scope_root(None)`` returns ``workspace_root()`` silently, and an explicit
            # ``session_id=None`` was measured writing a canonical record into the
            # ordinary root before the refusals were added.)
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
            "`If-Match` was omitted. Every write requires the record's current "
            "`ETag`, so a blind overwrite is not possible."
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
_STRONG_TAG_RE = re.compile(r'^"[^"\\]+"$')


def _expected_rev_from_token(token: str | None) -> int | None:
    """The integer after the LAST ``.`` of a client token, else ``None``."""
    if not token or "." not in token:
        return None
    try:
        return int(token.rsplit(".", 1)[-1])
    except (TypeError, ValueError):
        return None


def _precondition_required(exp) -> JSONResponse:
    return JSONResponse(
        status_code=428,
        content={"error": "precondition_required", "experiment_id": exp.id},
    )


def _malformed_if_match(exp) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": "malformed_if_match",
            "experiment_id": exp.id,
            "message": "If-Match must be one or more strong quoted validators.",
        },
    )


def _stale_write(exp, expected_token: str | None) -> JSONResponse:
    resp = JSONResponse(
        status_code=412,
        content={
            "error": "stale_write",
            "experiment_id": exp.id,
            "expected_rev": _expected_rev_from_token(expected_token),
            "current_rev": exp.rev,
            "expected_version": expected_token,
            "current_version": exp.version_token(),
        },
    )
    # Echo the CURRENT strong validator so the client can refresh in one hop.
    resp.headers["ETag"] = exp.etag()
    return resp


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


def _summary(exp: Experiment) -> dict:
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
        "status": exp.status(),
        "created_utc": exp.created_utc,
        "pending_count": exp.pending_count(),
        "evidenced_field_count": exp.evidenced_field_count(),
        "exported": exp.exported(),
        "record_id": exp.record_id,
    }


def _detail(exp: Experiment) -> dict:
    detail = _summary(exp)
    record_path = exp.record_path()
    sidecar_path = exp.sidecar_path()
    detail.update(
        {
            "draft_ok": exp.draft_ok(),
            # P30.6 — SAFE basename only, never the absolute server/mount path
            # (CLAUDE.md path-boundary rules). The client labels + names the
            # download from the filename; JSON content comes from /artifacts.
            "artifact_refs": {
                "record_filename": record_path.name if exp.exported() and record_path else None,
                "sidecar_filename": sidecar_path.name if exp.exported() and sidecar_path else None,
            },
            "source_files": (exp.source or {}).get("files") or [],
            "workflow": derive_workflow(
                pending_count=exp.pending_count(),
                draft_ok=exp.draft_ok(),
                ready=exp.export_ready(),
                exported=exp.exported(),
                rev=exp.rev,
            ),
            # Derived exported-artifact freshness (P28.2): none | current | stale.
            "artifact": dependencies.artifact_state(exp),
        }
    )
    return detail


def _workflow_for(exp: Experiment) -> dict:
    """Derive the workflow from an experiment's current signals (same call as
    ``_detail``). Used to capture the pre-mutation step states and to surface the
    post-mutation workflow on a mutation response."""
    return derive_workflow(
        pending_count=exp.pending_count(),
        draft_ok=exp.draft_ok(),
        ready=exp.export_ready(),
        exported=exp.exported(),
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
        "its result and can never fail a container probe."
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
                    "detail": (
                        f"official schema valid: "
                        f"{result.official_report.ok if result.official_report else False}"
                    ),
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
        "classification that no longer held. A missing digest is `428`, a stale one "
        "is `412`, and neither mutates anything. Every response carries the CURRENT "
        "digest, so a `412` can be recovered from in one further request.\n\n"
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
                "Refused without mutating: the `plan_digest` does not match the "
                "current workspace, so it changed after the preview the operator "
                "approved. The response carries the current `plan_digest`; preview "
                "again and let the operator re-approve what they would now lose."
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
        "any other record. Read-only, and it states no validity verdict."
    ),
    response_description="Every experiment as a summary row.",
    responses={**_R_UNAUTHORIZED, **_R_TUTORIAL_SCOPE},
)
def list_experiments(scope: TutorialScopeDep) -> dict:
    return {"experiments": [_summary(e) for e in ws.list_experiments(scope)]}


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
    responses={**_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
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


@router.get(
    "/experiments/{experiment_id}/pending",
    tags=[TAG_DRAFTS],
    summary="List a Record's Open Blocking Questions",
    description=(
        "The questions that are still blocking this draft, each with the stable "
        "key an answer must be submitted under, what the question is about, and — "
        "for the built-in examples only — a clearly labelled suggested "
        "answer that is never applied automatically. Read-only; the response "
        "carries the record's current `ETag`."
    ),
    response_description="The open blocking questions, with the current `ETag`.",
    responses={**_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def get_pending(scope: TutorialScopeDep, experiment_id: ExperimentId, response: Response):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    response.headers["ETag"] = exp.etag()
    return serialize.pending_to_list(
        exp.draft, ws.load_demo_answers(), example_scope=_example_scope(experiment_id)
    )


# --- 7. answers ---------------------------------------------------------------


def _answers_to_apply_shape(answers_by_id: dict, draft: dict, timestamp: str) -> dict:
    """Translate UI answers (keyed by blocker id/about) into ``apply_answers`` input.

    Only values literally present are forwarded; blank/missing answers are dropped, so the
    core never invents. Asset blockers key on their URI; ``series``/``descriptor``/``edge``
    key on their kind name.
    """
    pending = draft.get("pending") or []
    # An asset key is recognized if it names a still-pending asset blocker (the
    # /answers fill path) OR an asset already present in the draft (the /edit
    # correction path, where 0 pending means no blocker carries the uri). The union
    # leaves /answers behaviour unchanged — a pending asset is never yet in
    # draft["assets"], so its uri is still recognized exactly as before.
    asset_uris = {e.get("uri") for e in pending if e.get("kind") == "asset"}
    asset_uris |= {a.get("uri") for a in (draft.get("assets") or []) if isinstance(a, dict)}
    out: dict = {"timestamp": timestamp, "asset_sha256": {}}
    for key, value in (answers_by_id or {}).items():
        if value in (None, ""):
            continue
        if key in asset_uris:
            out["asset_sha256"][key] = value
        elif key in ("series", "descriptor", "descriptor_label", "edge"):
            out[key] = value
        # Unknown keys are ignored — never invented into the draft.
    return out


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
        "`If-Match`. Blank and unrecognised answers are dropped rather than "
        "invented, so a submission that changes nothing is a no-op: it is not "
        "logged and does not advance the revision."
    ),
    response_description=(
        "The refreshed blocking questions, status, revision metadata, workflow, "
        "and the downstream invalidation, with the new `ETag`."
    ),
    responses={
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        **_R_PRECONDITION,
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
            "Omitting `confirmed_by_user: true` is rejected with `422`, and a key "
            "that names no open question is ignored rather than invented."
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
        apply_shape = _answers_to_apply_shape(body.get("answers") or {}, exp.draft, timestamp)
        exp.draft = apply_answers(exp.draft, apply_shape)
        # answer_log is EXCLUDED from the rev signature: log the submission only when it
        # actually changes the authoritative draft, so an identical re-entry is neither
        # logged nor rewritten (byte-stable) and never bumps rev. save_versioned decides
        # by comparing the on-disk authoritative signature.
        exp.answer_log.append({"applied": apply_shape, "at": timestamp})
        changed = exp.save_versioned()
        if not changed:
            exp.answer_log.pop()  # no-op re-entry: discard the speculative log append
        # Derived downstream invalidation (P28.2) at the post-mutation revision. A
        # byte-stable no-op reports changed=False with empty deltas and no rev bump.
        changed_fields = submitted_fields if changed else []
        invalidation = dependencies.build_invalidation(
            changed=changed,
            changed_fields=changed_fields,
            pre_steps=pre_steps,
            post_exp=exp,
        )
        result = serialize.pending_to_list(
            exp.draft, ws.load_demo_answers(), example_scope=_example_scope(experiment_id)
        )
        result["status"] = exp.status()
        result.update(vc.version_fields(exp))
        result["workflow"] = _workflow_for(exp)
        result["invalidation"] = invalidation
        response.headers["ETag"] = exp.etag()
        return result


# --- 7b. edit (correct an already-answered field) -----------------------------


def _has_correction_target(apply_shape: dict) -> bool:
    """True iff ``apply_shape`` names at least one recognized correction field.

    An asset sha256 (keyed by a known uri), a series/descriptor/edge value. A bare
    ``descriptor_label`` (or only ``timestamp``/``asset_sha256:{}``) is NOT an
    actionable correction — an edit body that reduces to nothing recognized is
    rejected (422) rather than silently no-op'd, so an unknown field is never
    quietly swallowed.
    """
    return bool(apply_shape.get("asset_sha256")) or any(
        k in apply_shape for k in ("series", "descriptor", "edge")
    )


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
        "with `422` rather than silently doing nothing, and a value that fails the "
        "core's own checks leaves the stored value unchanged. It never reopens or "
        "creates a blocking question."
    ),
    response_description=(
        "The refreshed blocking questions, status, revision metadata, workflow, "
        "and the downstream invalidation, with the new `ETag`."
    ),
    responses={
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        **_R_PRECONDITION,
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
        apply_shape = _answers_to_apply_shape(body.get("answers") or {}, exp.draft, timestamp)
        if not _has_correction_target(apply_shape):
            # No recognized field to correct — never invent one.
            return JSONResponse(
                status_code=422,
                content={
                    "error": "unrecognized_field",
                    "message": "No editable field was recognized in the request.",
                },
            )
        # OVERWRITE the current value(s) for the recognized keys, recording a fresh
        # user_confirmation. apply_corrections never touches pending and never
        # invents a value (a malformed sha256 / off-enum qc leaves the value as-is).
        exp.draft = apply_corrections(exp.draft, apply_shape)
        exp.answer_log.append({"edited": apply_shape, "at": timestamp})
        changed = exp.save_versioned()
        if not changed:
            exp.answer_log.pop()  # byte-stable no-op: discard the speculative log append
        changed_fields = submitted_fields if changed else []
        invalidation = dependencies.build_invalidation(
            changed=changed,
            changed_fields=changed_fields,
            pre_steps=pre_steps,
            post_exp=exp,
        )
        result = serialize.pending_to_list(
            exp.draft, ws.load_demo_answers(), example_scope=_example_scope(experiment_id)
        )
        result["status"] = exp.status()
        result.update(vc.version_fields(exp))
        result["workflow"] = _workflow_for(exp)
        result["invalidation"] = invalidation
        response.headers["ETag"] = exp.etag()
        return result


# --- 8. export ----------------------------------------------------------------


def _write_record(exp: Experiment, result) -> None:
    """Write record + sidecar into the experiment records dir and mark it exported."""
    exp.records_dir.mkdir(parents=True, exist_ok=True)
    exp.record_id = result.record["record_id"]
    record_path = exp.records_dir / f"{exp.record_id}.json"
    sidecar_path = exp.records_dir / f"{exp.record_id}.evidence.json"
    atomic_write_text(record_path, json.dumps(result.record, indent=2) + "\n")
    atomic_write_text(sidecar_path, json.dumps(result.sidecar, indent=2) + "\n")


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
        "A gated failure also returns `200`, with `ok: false`, the failing draft "
        "and official reports, and a flat `errors` list — decide by reading `ok`, "
        "not the status code. Nothing is written in that case.\n\n"
        "Requires the record's current `ETag` in `If-Match`. Exported records are "
        "immutable: exporting a record that already has one is refused."
    ),
    response_description=(
        "The export result. `ok: true` means the record and sidecar were written; "
        "`ok: false` means the gate refused and nothing was written."
    ),
    responses={
        **_R_UNAUTHORIZED,
        **_R_EXPERIMENT_NOT_FOUND,
        **_R_PRECONDITION,
        409: {
            "description": (
                "This record has already been exported. Records are immutable, so "
                "nothing was overwritten."
            )
        },
    },
)
def post_export(
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
        record_path = exp.records_dir / f"{exp.id}.json"
        sidecar_path = exp.records_dir / f"{exp.id}.evidence.json"
        if exp.exported() and record_path.exists() and sidecar_path.exists():
            return JSONResponse(
                status_code=409,
                content={
                    "error": "record_exists",
                    "message": f"{record_path.name} already exists; records are immutable.",
                    "record_id": exp.id,
                },
            )
        if not exp.exported() and record_path.exists():
            # RECONCILIATION: not exported, yet an artifact exists — the crash window
            # above. Proceed and republish from the CURRENT draft (the orphan may be
            # a projection of an older draft, so it is replaced, never adopted). Warn
            # so an operator sees that a fault happened rather than the repair being
            # silent. Path-free by rule: the record id and the BASENAME only, never a
            # filesystem path (P30.6, and a log line is an exfiltration surface too).
            #
            # `not exp.exported()` is EXPLICIT (it was implied by the fall-through
            # before the sidecar clause above existed). This warning means exactly one
            # thing — "state and disk disagree about whether an export happened" — and
            # an exported record missing one of its files is NOT that: state and disk
            # agree an export happened, one file is simply gone. That is the same
            # class as the mirror case, which is deliberately silent (see
            # `test_no_reconciliation_warning_on_the_mirror_case`), so both self-heals
            # stay silent and the warning keeps one unambiguous meaning.
            _log.warning(
                "export reconciliation: record %s has an orphan artifact %s on disk "
                "while its state says not exported (a fault between the artifact "
                "write and the state save); republishing from the current draft",
                exp.id,
                record_path.name,
            )

        result = export_draft(exp.draft, REPO_ROOT, record_id=exp.id)
        payload = serialize.export_result_to_dict(result)
        if not result.ok:
            # Nothing written. Surface the failing reports and a flat errors list.
            # No mutation happened, so report an honest changed=False invalidation
            # (never fabricate a mutation that did not occur).
            errors = []
            if payload["official_report"]:
                errors = payload["official_report"]["errors"]
            elif not result.draft_report.ok:
                errors = payload["draft_report"]["errors"]
            payload["errors"] = errors
            payload["workflow"] = _workflow_for(exp)
            payload["invalidation"] = dependencies.build_invalidation(
                changed=False, changed_fields=[], pre_steps=pre_steps, post_exp=exp
            )
            return JSONResponse(status_code=200, content=payload)

        _write_record(exp, result)
        # export normally changes the authoritative state (record_id: None -> id), so
        # this bumps rev and stamps updated_utc, persisting the state atomically. On a
        # self-heal of an already-exported record `record_id` is ALREADY set, the
        # authoritative signature is unchanged, and it returns False without rewriting
        # anything — a filesystem repair, not a scientific state change.
        #
        # P4 review FIX E — that return value is PASSED THROUGH to the invalidation,
        # exactly as the two sibling mutation handlers do (`post_answers`,
        # `post_edit`). It used to be hardcoded `changed=True, ["record_id"]`, which on
        # the self-heal path contradicted the same response's own `rev` (unchanged),
        # its ETag (unchanged) and this handler's own failure-branch rule ("never
        # fabricate a mutation that did not occur").
        changed = exp.save_versioned()
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


# --- 9. validate --------------------------------------------------------------


@router.post(
    "/experiments/{experiment_id}/validate",
    tags=[TAG_VALIDATION],
    summary="Validate a Record Against the Official Schema",
    description=(
        "Checks this record against the vendored official ISAAC schema and returns "
        "`ok`, a list of `{path, message}` errors, the schema label, and whether "
        "the check was a dry run.\n\n"
        "For an already-exported record the written record is validated "
        "(`dry_run: false`). Otherwise the export is run in memory and the "
        "resulting candidate record is validated without writing anything "
        "(`dry_run: true`). Read-only in both cases. The verdict comes from the "
        "same deterministic core function the command line uses.\n\n"
        "If the written record cannot be read at all, no verdict is invented: the "
        "operation reports `ok: false` with the single fixed error `Validation "
        "could not be completed.` and `dry_run: false`. Read that as *no verdict*, "
        "not as a schema violation — the artifacts operation reports why the file "
        "could not be read."
    ),
    response_description="The official-schema verdict, its errors, and whether it was a dry run.",
    responses={**_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def post_validate(scope: TutorialScopeDep, experiment_id: ExperimentId):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)

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
            }
        report = validate_official(record, REPO_ROOT)
        return {
            "ok": report.ok,
            "errors": [{"path": e.path, "message": e.message} for e in report.errors],
            "schema": SCHEMA_LABEL,
            "dry_run": False,
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
    except Exception:
        # Defensive: never 500, and never interpolate the exception (path/stack/
        # secret) into the client response. Return a fixed, path-free message and
        # log the real detail server-side for operators.
        _log.exception("validate dry-run failed experiment=%s", experiment_id)
        ok, errors = False, [{"path": "$", "message": "Validation could not be completed."}]

    return {"ok": ok, "errors": errors, "schema": SCHEMA_LABEL, "dry_run": True}


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
        "workspace involved. Returns `ok`, a rendered summary line, the "
        "`{path, message}` errors, and the schema version checked against.\n\n"
        "It calls the same authoritative validator over the same vendored schema "
        "that the per-experiment validation operation uses, so the two verdicts "
        "agree by construction. The body is never written anywhere and its content "
        "is never logged; only the outcome and error count are.\n\n"
        "Send the record as a raw JSON body. The body is read in memory under a "
        "hard size limit."
    ),
    response_description="The official-schema verdict, a rendered summary, and the errors.",
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
    calls for exported records — verdict parity is by construction (same
    function, same schema), not a second reimplementation.

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
        "validate_record outcome=ok ok=%s error_count=%d warning_count=%d",
        report.ok,
        len(report.errors),
        len(warnings.get("warnings", [])),
    )
    return {
        "ok": report.ok,
        "summary": report.render(),
        "errors": [{"path": e.path, "message": e.message} for e in report.errors],
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
    responses={**_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
)
def post_audit(scope: TutorialScopeDep, experiment_id: ExperimentId):
    exp = ws.load_experiment(experiment_id, session_id=scope)
    if exp is None:
        return _not_found(experiment_id)
    if not exp.exported():
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


def _warnings_payload(exp: Experiment) -> dict:
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
    "equivalent: both are read-only and return the same payload."
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
    responses={**_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
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
    responses={**_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
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
        "evidence envelopes, which are the sidecar's own source. Read-only."
    ),
    response_description="One evidence entry per field carrying a value.",
    responses={**_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
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
        # Deliberately NO new response field. The one honest thing a marker would add
        # — that the artifact pair is not readable — is already published by
        # `/artifacts` as `artifact.state: "stale"`, which this endpoint's only caller
        # fetches in the same `Promise.all`; and `api.ts::getEvidence` discards every
        # key except `evidence`, so a marker here would be unreachable weight on the
        # wire. The description above states the fallback instead.
        if exp.exported():
            _log.warning(
                "evidence: record %s is marked exported but its artifact pair could "
                "not be read; serving the draft evidence trail instead",
                exp.id,
            )
        entries = serialize.evidence_trail_from_draft(exp.draft)
    return {"evidence": entries}


# --- 12b. evidence classification (P28.5, evidence-support axis, read-only) ----

#: The five evidence-support classes, in the display precedence used everywhere.
#: The single source for the ``counts`` histogram key set.
_EVIDENCE_CLASSES = (
    "supported",
    "inferred_candidate",
    "insufficient_evidence",
    "conflicting_evidence",
    "unknown",
)


@router.get(
    "/experiments/{experiment_id}/evidence-classification",
    tags=[TAG_EVIDENCE],
    summary="Classify a Record's Evidence Support",
    description=(
        "Per-field evidence-support classification for this record's current "
        "state, plus a histogram over the five classes — `supported`, "
        "`inferred_candidate`, `insufficient_evidence`, `conflicting_evidence` and "
        "`unknown` — bound to the authoritative `record_rev` so a client can tell "
        "when its view is stale.\n\n"
        "This carries the evidence-support axis only. It deliberately reports no "
        "validity, completion, exportability, or advisory verdict; those live in "
        "their own operations. Read-only, and it takes no lock."
    ),
    response_description=(
        "The per-field classifications, the five-class histogram, and the "
        "revision they describe."
    ),
    responses={**_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
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
        "payloads rather than an error. Read-only."
    ),
    response_description=(
        "The record and sidecar JSON with their filenames, or nulls when nothing "
        "has been exported."
    ),
    responses={**_R_UNAUTHORIZED, **_R_EXPERIMENT_NOT_FOUND},
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
        return {
            "record": None,
            "sidecar": None,
            "record_filename": None,
            "sidecar_filename": None,
            # Single-sourced: for a non-exported record this is
            # {"state": "none", "reason": None}.
            "artifact": dependencies.artifact_state(exp),
        }
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
                "distinct from a query that simply matched nothing."
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
        exps = ws.list_experiments(tutorial_session)  # hardened, read-race-safe snapshot
        wres = search.workspace_search(q, exps, limit=limit, offset=offset)
        normalized_query = wres.normalized_query
        query_too_short = wres.reason == search.QUERY_TOO_SHORT
        workspace_group = {
            "plane": search.PLANE,
            "provider": search.PROVIDER,
            "available": True,
            "reason": wres.reason,
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
    """
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
        pending=serialize.pending_to_list(exp.draft, ws.load_demo_answers()),
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
