"""Static SPA serving for single-container deployments.

In the k8s deployment one container serves both the API (``{base}/api/*``) and
the built Vite SPA (``{base}/...``). Locally this module is inert: it mounts
nothing unless ``ISAAC_STATIC_DIR`` points at a built ``dist/`` directory, so
dev keeps the two-process setup (uvicorn + Vite dev server) unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_spa(app: FastAPI, base: str) -> None:
    """Serve the built SPA from ``ISAAC_STATIC_DIR`` under ``base``.

    Called after the API router is registered, so real API routes always win
    over the catch-all (FastAPI matches in registration order). Unknown
    ``{base}/api/*`` paths keep JSON-404 semantics; everything else falls back
    to ``index.html`` for client-side routing.
    """
    static_dir = os.environ.get("ISAAC_STATIC_DIR", "").strip()
    if not static_dir:
        return
    dist = Path(static_dir).resolve()
    index = dist / "index.html"
    if not index.is_file():
        return  # fail soft: the API still serves without the SPA

    assets = dist / "assets"
    if assets.is_dir():
        app.mount(f"{base}/assets", StaticFiles(directory=assets), name="spa-assets")

    if base:

        @app.get(base, include_in_schema=False)
        def spa_root() -> FileResponse:  # GET /krish (no trailing slash)
            return FileResponse(index)

    @app.get(f"{base}/{{full_path:path}}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)  # e.g. vite.svg at the dist root
        return FileResponse(index)
