"""Shared-secret bearer auth for the hosted synthetic demo (Phase 20).

Presentation-layer only: unauthenticated requests are rejected before reaching
any route. Adds no validation logic and never touches the truth plane
(``isaac_records``). Auth is DISABLED when ``ISAAC_UI_API_KEY`` is unset or
empty, so local dev needs zero configuration.

Kept open on purpose:
- ``GET /api/health`` — platform health checks; exposes a liveness banner only.
- ``OPTIONS`` — CORS preflight carries no credentials by spec.
"""

from __future__ import annotations

import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_OPEN_PATHS = frozenset({"/api/health"})


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Require ``Authorization: Bearer <ISAAC_UI_API_KEY>`` on every /api route."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._expected = ""
        key = os.environ.get("ISAAC_UI_API_KEY", "").strip()
        if key:
            self._expected = f"Bearer {key}"

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._expected:
            return await call_next(request)
        if request.method == "OPTIONS" or request.url.path in _OPEN_PATHS:
            return await call_next(request)
        supplied = request.headers.get("authorization", "")
        if supplied and secrets.compare_digest(supplied, self._expected):
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "detail": "Missing or invalid API key."},
        )
