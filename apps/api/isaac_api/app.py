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
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from . import runtime_mode
from .providers import validate_provider_config_or_raise
from .auth import ApiKeyAuthMiddleware
from .config import base_path
from .experiment_repository import DurableWriteConflict, StorageUnavailable
from .identity import (
    HumanActorRequired,
    human_actor_required_handler,
    validate_edge_trust_verifier_or_raise,
)
from .routes import (
    OPENAPI_TAGS,
    TutorialScopeError,
    durable_write_conflict_handler,
    request_validation_error_handler,
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


#: Duplicated from ``isaac_api.mcp.deployment.DEPLOYMENT_ENV``, ON PURPOSE, and
#: pinned equal to it by ``test_mcp_transport.py`` so the copy cannot drift.
#:
#: It cannot be imported: reading the constant from the package would execute
#: ``isaac_api/mcp/__init__.py``, which is the entire thing
#: :func:`_mcp_is_requested` exists to avoid. See its docstring.
_MCP_DEPLOYMENT_ENV = "ISAAC_MCP_DEPLOYMENT"


def _mcp_is_requested() -> bool:
    """Did an operator ask for MCP at all? Answered WITHOUT importing the package.

    Deliberately a NECESSARY condition, not a sufficient one. It does not know
    which binding names serve a transport and must never learn: that registry
    lives in ``deployment.py``/``transport.py``, and a second copy here would
    silently refuse to mount the next binding somebody adds. A non-empty value of
    any kind therefore imports the package and lets
    :func:`~.mcp.transport.mcp_transport_or_none` make the real decision, which
    still fails closed for unset, empty, unrecognised, reserved and misconfigured.

    Why the cheap check exists at all: importing ``isaac_api.mcp`` executes
    ``policy.py``, whose module-scope ``OPERATIONS`` introspects
    ``routes.list_runs`` and RAISES ``RuntimeError`` on an unreviewed query
    parameter or an unrenderable annotation. Because ``app = create_app()`` runs at
    module scope (bottom of this file), an unconditional import turns that
    review-time guard into a boot failure for the WHOLE application — API, UI and
    health — on a deployment that was never going to serve MCP. The guard is
    correct and stays; what changes is that only an operator who asked for MCP can
    be stopped by it. ``test_mcp_transport.py`` pins both halves.
    """
    return bool((os.environ.get(_MCP_DEPLOYMENT_ENV) or "").strip())


def create_app() -> FastAPI:
    # Fail-closed at boot, BEFORE reading config or constructing the app: refuse
    # to construct when the runtime mode is misconfigured (invalid value, or
    # 'real' whose guardrails are not built), so a misconfigured container cannot
    # silently boot in a permissive state.
    runtime_mode.validate_runtime_mode_or_raise()
    # Same discipline, second configuration axis: refuse to construct when
    # ISAAC_EDGE_TRUST_VERIFIER names a verifier this build does not have. The
    # resolver itself fails CLOSED (an unrecognised value yields the verifier that
    # identifies nobody), so without this the deployment would boot looking
    # correctly configured while checking nothing — the operator who set the
    # variable would believe identity was being established when it was not.
    #
    # No route consumes identity today; this is here so the misconfiguration
    # cannot arrive silently ahead of the slice that does.
    validate_edge_trust_verifier_or_raise()
    # The SAME fail-closed discipline for the three AI provider seams, and it is
    # here rather than left to the seams' own resolution for the reason the line
    # above exists: resolution itself never raises — an unset, empty or
    # unrecognised value falls to `unconfigured`, which is the safe state and must
    # stay silent. That is right for a value nobody set, and wrong for a value
    # somebody set and mistyped. Without this call a container deployed with
    # `ISAAC_ASSISTANT_PROVIDER=anthropc` boots happily with no assistant, and the
    # first person to notice is a scientist wondering why nothing answers.
    validate_provider_config_or_raise()
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
    # An attributability refusal — the operation records who performed it and this
    # deployment could not establish who is calling. Raised from
    # `identity.require_human_actor`, which is a FastAPI dependency and so cannot
    # return a response, only raise.
    #
    # REGISTERED HERE BECAUSE A ROUTE NOW CONSUMES THAT DEPENDENCY, AND THE
    # REGISTRATION IS NOT OPTIONAL. `HumanActorRequired`'s own docstring has said,
    # since it was written, that the handler is deliberately NOT registered while
    # nothing raises it, and that "the route slice that first consumes the dependency
    # must register it in create_app in the same change; until then, raising this
    # from a live route would surface as a 500". `POST /api/experiments/{id}/submit`
    # is that slice. Without this line every submission in the default build — which
    # is every deployment, because no verifier is configured anywhere — would return
    # a bare 500 with a traceback in the server log instead of the typed 409 that
    # tells the caller nothing was written and why.
    app.add_exception_handler(HumanActorRequired, human_actor_required_handler)
    # A request body too deeply nested for FastAPI's OWN 422 handler to render.
    #
    # THIS ONE REPLACES A DEFAULT RATHER THAN ADDING A CASE, which is why it is
    # worth a note. FastAPI installs `request_validation_exception_handler` for
    # `RequestValidationError`; that handler echoes the offending `input` back
    # through `jsonable_encoder`, which recurses per level, so a ~1,000-deep body
    # destroyed the handler that exists to refuse it and the caller got an
    # unhandled 500 instead of a 422 — on most POSTs in this application. The
    # record was never at risk (the route function is not entered), but the
    # refusal was unreadable and named nothing.
    #
    # The replacement is byte-identical to FastAPI's for every request whose
    # `input` is renderable, and bounds only what is ECHOED — never what is
    # accepted. See the handler's docstring for the derivation of the bound and
    # for why the depth predicate is the application's existing iterative one.
    app.add_exception_handler(
        RequestValidationError, request_validation_error_handler
    )
    # ISAAC_BASE_PATH prefixes every route (the router keeps its own /api
    # prefix, so routes land at {base}/api/*). Unset, prefix="" is byte-identical
    # to the historical behavior. mount_spa is a no-op unless ISAAC_STATIC_DIR
    # points at a built frontend; registered last so API routes win.
    app.include_router(router, prefix=base)
    # --- MCP Streamable HTTP transport, mounted ONLY when configured ----------
    # `mcp_transport_or_none` returns None unless ISAAC_MCP_DEPLOYMENT resolves to
    # a binding that declares `serves_transport` — which nothing does by default,
    # because every unset/empty/unrecognised/reserved/misconfigured value fails
    # closed to the unconfigured binding. So the DEFAULT DEPLOYMENT REGISTERS NO
    # MCP ROUTE AT ALL. That is the point, and it is not the same as a route that
    # answers 403: a path that refuses still advertises that ISAAC speaks MCP and
    # is one conditional away from being opened by whoever reads the 403 as a bug.
    #
    # Imported here rather than at module scope so the whole feature is one
    # contiguous block, and — since `_mcp_is_requested()` gates the import —
    # so an application that will never serve it does not import the package at
    # all. That is a boot-availability property, not tidiness: `policy.py` raises
    # at import on an unreviewed `list_runs` query parameter, and with
    # `app = create_app()` at module scope an unconditional import would turn that
    # review-time guard into "uvicorn cannot start". Read `_mcp_is_requested`
    # before changing this. Registered BEFORE `mount_spa`, whose catch-all would
    # otherwise swallow the path.
    #
    # An exact `Route`, not `app.mount`: a Mount matches a PREFIX, which would
    # make `{base}/api/mcp/anything` the transport's problem to 404 and would
    # 307-redirect the canonical trailing-slash-free URL that `claude mcp add
    # --transport http` is given. A Starlette `Route` whose endpoint is an object
    # rather than a function is treated as a raw ASGI app, which is exactly what
    # the transport is. `methods=None` matches every verb so the transport can
    # answer GET and DELETE with its own reasons rather than a bare 405, and
    # `include_in_schema=False` keeps a non-OpenAPI protocol out of the OpenAPI
    # document (a plain Route is invisible to FastAPI's generator anyway).
    if _mcp_is_requested():
        from starlette.routing import Route

        from .mcp.transport import MCP_PATH, mcp_transport_or_none

        mcp_transport = mcp_transport_or_none(app)
        if mcp_transport is not None:
            app.router.routes.append(
                Route(
                    f"{base}{MCP_PATH}",
                    mcp_transport,
                    name="mcp",
                    methods=None,
                    include_in_schema=False,
                )
            )
    # -------------------------------------------------------------------------
    mount_spa(app, base)
    return app


app = create_app()
