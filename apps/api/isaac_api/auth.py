"""Shared-secret bearer auth for the hosted synthetic demo (Phase 20).

Presentation-layer only: unauthenticated requests are rejected before reaching
any route. Adds no validation logic and never touches the truth plane
(``isaac_records``). Auth is DISABLED when ``ISAAC_UI_API_KEY`` is unset or
empty, so local dev needs zero configuration.

When enabled, this covers every route in the app — including FastAPI's auto
``/docs`` and ``/openapi.json`` — not just ``/api/*``. Kept open on purpose:
- ``GET /api/health`` — platform health checks; exposes a liveness banner only.
- ``OPTIONS`` — CORS preflight carries no credentials by spec.
"""

from __future__ import annotations

import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import base_path


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Require ``Authorization: Bearer <ISAAC_UI_API_KEY>`` on every route except
    ``GET {base}/api/health`` and ``OPTIONS``."""

    def __init__(self, app) -> None:
        super().__init__(app)
        # Health stays open at the deployed base path so platform/pod probes
        # never need credentials ({"/api/health"} when ISAAC_BASE_PATH is unset).
        self._open_paths = frozenset({f"{base_path()}/api/health"})
        self._expected = ""
        key = os.environ.get("ISAAC_UI_API_KEY", "").strip()
        if key:
            self._expected = f"Bearer {key}"

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._expected:
            return await call_next(request)
        if request.method == "OPTIONS" or request.url.path in self._open_paths:
            return await call_next(request)
        supplied = request.headers.get("authorization", "")
        # Compare as bytes: compare_digest raises TypeError on non-ASCII str,
        # and header values arrive latin-1 decoded — bytes keeps malformed
        # input a clean constant-time False (401) instead of a 500.
        if supplied and secrets.compare_digest(
            supplied.encode("utf-8"), self._expected.encode("utf-8")
        ):
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "detail": "Missing or invalid API key."},
        )
