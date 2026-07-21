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
from .auth import ApiKeyAuthMiddleware
from .config import base_path
from .routes import router
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
    base = base_path()
    app = FastAPI(
        title="ISAAC Metadata Assistant — local UI backend",
        version=__version__,
        summary="Synthetic-only FastAPI wrapper over the deterministic isaac_records core.",
    )
    # Order matters: Starlette treats the LAST-added middleware as outermost.
    # Auth is added first so CORSMiddleware wraps it — preflight short-circuits
    # in CORS, and auth 401s still get CORS headers the browser can read.
    app.add_middleware(ApiKeyAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    # ISAAC_BASE_PATH prefixes every route (the router keeps its own /api
    # prefix, so routes land at {base}/api/*). Unset, prefix="" is byte-identical
    # to the historical behavior. mount_spa is a no-op unless ISAAC_STATIC_DIR
    # points at a built frontend; registered last so API routes win.
    app.include_router(router, prefix=base)
    mount_spa(app, base)
    return app


app = create_app()
