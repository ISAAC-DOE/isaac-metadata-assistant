"""FastAPI application factory for the ISAAC local UI prototype.

Local-first and synthetic-only. Run it with::

    .venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000

By default it permits CORS only from the Vite dev server (localhost:5173 /
127.0.0.1:5173); deployed environments override the allowlist with the
ISAAC_UI_CORS_ORIGINS env var (comma-separated origins). Remote binding is a
deployment concern (the container CMD passes --host 0.0.0.0); local runs keep
127.0.0.1. It imports and calls the deterministic core (``isaac_records``) in-process,
so the UI gets byte-identical verdicts to the CLI.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from . import runtime_mode
from .auth import ApiKeyAuthMiddleware
from .config import base_path
from .experiment_repository import DurableWriteConflict, StorageUnavailable
from .routes import (
    OPENAPI_TAGS,
    TutorialScopeError,
    durable_write_conflict_handler,
    router,
    storage_unavailable_handler,
    tutorial_scope_error_handler,
)
from .spa import mount_spa

# Default: the Vite dev server origins. Deployed environments override via
# ISAAC_UI_CORS_ORIGINS (comma-separated full origins, e.g. the Vercel domain).
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _cors_origins() -> list[str]:
    raw = os.environ.get("ISAAC_UI_CORS_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)


def create_app() -> FastAPI:
    # Fail-closed at boot, BEFORE reading config or constructing the app: refuse
    # to construct when the runtime mode is misconfigured (invalid value, or
    # 'real' whose guardrails are not built), so a misconfigured container cannot
    # silently boot in a permissive state.
    runtime_mode.validate_runtime_mode_or_raise()
    # Deploy base path (ISAAC_BASE_PATH); "" locally. Resolved once and applied
    # to the router prefix and the SPA mount below.
    base = base_path()
    app = FastAPI(
        # P1: was "ISAAC Metadata Assistant — local UI backend". This title is
        # rendered verbatim in the hosted Endpoint Explorer's Quick Start line,
        # where "local" is simply false — the same document serves the hosted
        # deployment. The name now states what the thing is, not where it runs.
        title="ISAAC Metadata Assistant API",
        version=__version__,
        # Slice 2A: the old summary ("Synthetic-only FastAPI wrapper over the
        # deterministic isaac_records core.") was a flat whole-API claim, and this
        # API now also publishes a read-only database diagnostic. The synthetic
        # guarantee is scoped to the workspace; the diagnostic is named, not denied.
        #
        # AND THE WORKSPACE IS NO LONGER AN "EXAMPLE" ONE. The five built-in example
        # records used to be materialised into the ordinary workspace on every read;
        # they are created only inside a worked-example session, and on a FRESH
        # deployment the ordinary workspace is empty and stays empty until something
        # explicitly creates a record in it. So "a synthetic-only example workspace"
        # named this scope after content this build never puts there — the same defect
        # already corrected in the mode chip and on the Statistics page.
        #
        # NOTE THE "on a fresh deployment" QUALIFIER, which this comment previously
        # dropped: the claim is about what the build DOES, not about what the directory
        # holds. ``list_experiments(None)`` enumerates whatever is on disk and there is
        # no startup migration, so a workspace that already held the five still lists
        # them. Both scopes are now named, because both exist.
        summary=(
            "FastAPI wrapper over the deterministic isaac_records core: a "
            "synthetic-only workspace, isolated worked-example sessions holding the "
            "built-in example records, and one read-only, aggregate-only database "
            "diagnostic."
        ),
        # Documentation metadata only (consumed when the OpenAPI document is
        # generated, never at request time): the group descriptions for the tags
        # the routes carry. Defined next to the routes so the names cannot drift.
        openapi_tags=OPENAPI_TAGS,
        description=(
            "Every verdict this API reports is produced by the deterministic "
            "`isaac_records` core, in process, so an answer here is byte-identical "
            "to the same check run from the command line. The official ISAAC record "
            "schema is the only authority on record validity.\n\n"
            "Two planes are kept strictly separate. The truth plane decides "
            "validity, completeness and exportability. The Project Memory plane "
            "returns leads and provenance to confirm against the cited files — it "
            "never issues a correctness ruling and cannot authorise an export.\n\n"
            "Nothing here guesses. A value that is not supported by evidence stays "
            "missing or becomes a blocking question, and a question the assistant "
            "cannot answer from its fixed catalog is refused rather than invented.\n\n"
            # P36V: the earlier wording ("only the committed synthetic fixtures
            # can be read") was the loosest sentence in this description. No
            # uploaded FILE is read, but the CSV-preview and record-validator
            # operations do parse caller-supplied text. The frontend copy already
            # says so plainly; this prose is now held to the same standard.
            #
            # P1 review: "seeded" is load-bearing and was briefly lost to "built".
            # The workspace is not built only from committed content — a confirmed
            # answer or an edit is persisted into the record's state file, which a
            # measured canary proved. "Seeded" scopes the claim to materialisation,
            # which is the only form of it that is true. The third sentence exists
            # because the two before it, read together, otherwise implied that
            # nothing a caller supplies is ever stored.
            "This deployment runs in a synthetic-only data mode: file upload is "
            "always refused and the workspace is seeded only from committed "
            "reference files. Two operations do parse text you supply in the "
            "request body — the CSV preview and the standalone record validator — "
            "and neither stores what it reads. The answers and edits you confirm "
            "are stored, in the record's workspace state, so once you have worked "
            "on a record the workspace holds your input as well as the committed "
            "content it was seeded from.\n\n"
            # Slice 2A: the paragraph above reads as an exhaustive account of what
            # data this deployment touches, and it no longer is. Same wording the
            # frontend's reviewed governance copy carries, so the two cannot drift.
            "Separately, this deployment may run a protected, read-only diagnostic "
            "against an isolated SLAC test database containing production-derived "
            "records: those records are processed transiently in pod memory, only "
            "sanitized aggregate results are returned, no record is modified, no "
            "per-record content is displayed, and nothing is sent to any model. "
            "Database-backed record display remains disabled pending an explicit "
            "visibility decision."
        ),
    )
    # Order matters: Starlette treats the LAST-added middleware as outermost.
    # Auth is added first so CORSMiddleware wraps it — preflight short-circuits
    # in CORS, and auth 401s still get CORS headers the browser can read.
    app.add_middleware(ApiKeyAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=False,
        # THE RULE, not a per-verb rationale: this list must contain every HTTP
        # method any registered route uses, plus OPTIONS for the preflight itself.
        # A method missing here is not a partial failure — the browser's preflight
        # is refused (400, "Disallowed CORS method") and the real request is never
        # sent, so the route becomes unreachable from every cross-origin caller
        # (the Vite dev server, both Playwright suites, any deployment whose
        # frontend is served from another origin) while continuing to work in the
        # single-origin hosted deployment, which is exactly how PATCH shipped
        # broken: TestClient issues no preflight and the frontend tests mock fetch.
        # `test_cors_methods.py` derives the required set from the app's own route
        # table and fails if this list stops covering it — do not hand-maintain it
        # by adding a clause per verb.
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["ETag"],
    )
    # Scope-resolution refusals (a malformed or unknown worked-example session id)
    # are raised from a dependency, which cannot return a response. This renders them
    # with the same typed `{"error": ...}` body shape every other refusal uses.
    app.add_exception_handler(TutorialScopeError, tutorial_scope_error_handler)
    # A durable-storage outage — the deployment is configured to store experiments
    # in its own database and that database did not take the write. Registered on
    # the APP rather than handled per route because `Experiment.save()` is called
    # from a dozen operations (answers, corrections, edits, export) and every one
    # of them would otherwise surface a driver failure as an unhandled 500. One
    # handler is also what keeps the body identical wherever it is raised.
    #
    # It renders 503, never 500, and never a silent fall back to the filesystem —
    # see the handler's own docstring for why each of those is deliberate.
    app.add_exception_handler(StorageUnavailable, storage_unavailable_handler)
    # A refused durable write (the compare-and-swap declined it) that reached the
    # app without a handler of its own. The three mutation routes render their own
    # 412 with the full body; this catches `POST /api/experiments`, whose create
    # persists directly. Registered for the same reason as the line above: a new
    # exception class with an unguarded call site surfaces as a 500, and a
    # concurrency refusal is the one failure of the three that is not a server
    # error at all.
    app.add_exception_handler(DurableWriteConflict, durable_write_conflict_handler)
    # ISAAC_BASE_PATH prefixes every route (the router keeps its own /api
    # prefix, so routes land at {base}/api/*). Unset, prefix="" is byte-identical
    # to the historical behavior. mount_spa is a no-op unless ISAAC_STATIC_DIR
    # points at a built frontend; registered last so API routes win.
    app.include_router(router, prefix=base)
    mount_spa(app, base)
    return app


app = create_app()
