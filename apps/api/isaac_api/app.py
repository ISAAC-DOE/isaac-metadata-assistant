"""FastAPI application factory for the ISAAC local UI prototype.

Local-first and synthetic-only. Run it with::

    .venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000

It binds 127.0.0.1 by design (no remote listener in v1) and only permits CORS from the
Vite dev server (localhost:5173 / 127.0.0.1:5173). It imports and calls the deterministic
core (``isaac_records``) in-process, so the UI gets byte-identical verdicts to the CLI.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .routes import router

# The Vite dev server origins the browser client is served from.
CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="ISAAC Metadata Assistant — local UI backend",
        version=__version__,
        summary="Synthetic-only FastAPI wrapper over the deterministic isaac_records core.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
